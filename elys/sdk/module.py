# module: декораторы только собирают метаданные, регистрация — в attach().

from __future__ import annotations

import asyncio
import html
import logging
import traceback
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from functools import wraps
from time import perf_counter
from typing import Any, Protocol, TypeVar

from pyrogram import Client
from pyrogram import filters as filters_api
from pyrogram.filters import Filter
from pyrogram.handlers import (
    CallbackQueryHandler,
    DeletedMessagesHandler,
    EditedMessageHandler,
    InlineQueryHandler,
    MessageHandler,
    RawUpdateHandler,
)
from pyrogram.handlers.handler import Handler
from pyrogram.types import Message

from elys.core.loader import LoadError
from elys.core.registry import Resources, change_handler
from elys.core.router import Command, Router
from elys.core.scope import Scope
from elys.i18n import locales, translate
from elys.log import new_error_id
from elys.storage.kv import KV, Namespace
from elys.ui.emoji import unknown

from .config import Config
from .context import current
from .helpers import UserError, respond
from .html import E
from .loop import Loop

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
Hook = Callable[[Client], Awaitable[Any]]

_commands_log = logging.getLogger("elys.cmd")  # строка ▸ на каждую выполненную команду


class Host(Protocol):
    client: Client
    router: Router
    kv: KV


class Module:
    def __init__(self, name: str, *, version: str = "", author: str = "",
                 requires: Iterable[str] = (), config: Config | None = None,
                 strings: dict | None = None, banner: str = "") -> None:
        if not name or not name.strip():
            raise ValueError("модулю нужно имя")
        self.name, self.version, self.author = name, version, author
        self.requires, self.banner = tuple(requires), banner
        self.config = config if config is not None else Config()
        self.strings = strings or {}
        self.log = logging.getLogger(f"elys.mod.{name}")
        self.loaded = False
        self._app: Host | None = None
        self._resources = Resources(0)
        self._commands: list[Command] = []
        self._handlers: list[tuple[Handler, Scope | None]] = []
        self._bot_handlers: list[Handler] = []
        self._loops: list[Loop] = []
        self._on_ready: list[Hook] = []
        self._on_load: list[Hook] = []
        self._on_unload: list[Hook] = []
        self._group = 0
        self.listens_all = False  # есть вотчер без scope

    def __repr__(self) -> str:
        return f"<Module {self.name}>"

    @property
    def app(self) -> Host:
        if self._app is None:
            raise RuntimeError(f"{self.name} не загружен")
        return self._app

    @property
    def client(self) -> Client:
        return self.app.client

    @property
    def db(self) -> Namespace:
        return self.app.kv.ns(f"mod:{self.name}")

    @property
    def bot(self):
        return getattr(self.app, "bot", None)

    @property
    def commands(self) -> tuple[Command, ...]:
        return tuple(self._commands)

    def t(self, key: str, **values) -> str:
        strings = self.strings if any(key in s for s in self.strings.values()) else locales()
        return translate(strings, key, language=getattr(self.app, "language", "ru"),
                         premium=bool(getattr(self.app, "premium", False)), **values)

    # декораторы

    def command(self, name: str, *, aliases: Iterable[str] = (), roles: Iterable[str] = ()) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            self._commands.append(
                Command(
                    name.lower(),
                    self._guard_command(func),
                    self,
                    tuple(a.lower() for a in aliases),
                    frozenset(roles),
                )
            )
            return func

        return decorator

    def on_message(self, filters: Filter | None = None, *, scope: Scope | None = None) -> Callable[[F], F]:
        return self._watcher(MessageHandler, filters, scope, edited=False)

    def on_edited_message(self, filters: Filter | None = None, *, scope: Scope | None = None) -> Callable[[F], F]:
        return self._watcher(EditedMessageHandler, filters, scope, edited=True)

    def on_deleted_messages(self, filters: Filter | None = None):
        return self._extra_watcher(DeletedMessagesHandler, filters)

    def on_raw_update(self):
        return self._extra_watcher(RawUpdateHandler, None)

    def _extra_watcher(self, kind, filters):
        def decorator(func):
            self._handlers.append((kind(self._guard_watcher(func), filters), None))
            return func
        return decorator

    def callback(self, prefix: str):
        async def matches(_, client, query):
            return (query.from_user is not None and query.from_user.id == self.client.me.id
                    and isinstance(query.data, str) and query.data.startswith(prefix))
        return self._bot_watcher(CallbackQueryHandler, filters_api.create(matches))

    def inline(self, query: str):
        async def matches(_, client, update):
            return (update.from_user is not None and update.from_user.id == self.client.me.id
                    and update.query == query)
        return self._bot_watcher(InlineQueryHandler, filters_api.create(matches))

    def _bot_watcher(self, kind, filters):
        def decorator(func):
            self._bot_handlers.append(kind(self._guard_watcher(func), filters))
            return func
        return decorator

    def loop(self, interval: float, *, autostart: bool = False):
        def decorator(func):
            loop = Loop(self, func, interval, autostart)
            self._loops.append(loop)
            return loop
        return decorator

    def on_ready(self, func: Hook) -> Hook:
        self._on_ready.append(func)
        return func

    def on_load(self, func: Hook) -> Hook:
        self._on_load.append(func)
        return func

    def on_unload(self, func: Hook) -> Hook:
        self._on_unload.append(func)
        return func

    # рантайм

    async def form(self, message, text, buttons=(), **kwargs):
        return await self.app.inline.form(self, message, text, buttons, **kwargs)

    async def list(self, message, pages, **kwargs):
        return await self.app.inline.listing(self, message, pages, **kwargs)

    async def gallery(self, message, photos, **kwargs):
        return await self.app.inline.gallery(self, message, photos, **kwargs)

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        # фоновая задача модуля, отменяется при выгрузке.
        if not self.loaded:
            coro.close()
            raise RuntimeError(f"{self.name} не загружен")
        token = current.set(self.app)
        try:
            task = asyncio.get_running_loop().create_task(coro)
        finally:
            current.reset(token)
        self._resources.tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    @property
    def scopes(self) -> list[Scope]:
        return [scope for _, scope in self._handlers if scope is not None]

    async def attach(self, app: Host, group: int, *, resources: Resources | None = None) -> None:
        if self._app is not None:
            raise RuntimeError(f"{self.name} уже загружен")
        if self._bot_handlers and getattr(app, "bot", None) is None:
            raise LoadError("этому модулю нужен бот-помощник; перезапусти Elys для его подключения")
        self.config.bind(app.kv.ns(f"cfg:{self.name}"))
        app.router.add(*self._commands)
        self._app, self._group = app, group
        self._resources = resources or Resources(group, self.commands)
        self.loaded = True
        token = current.set(app)
        try:
            for handler, _ in self._handlers:
                await change_handler(app.client, handler, group)
                self._resources.handlers.append((app.client, handler))
            for handler in self._bot_handlers:
                await change_handler(self.bot, handler, group)
                self._resources.handlers.append((self.bot, handler))
            if self.listens_all:
                self.log.warning("вотчер без scope: гейт открыт для всех сообщений")
            for strings in self.strings.values():
                for text in strings.values():
                    if missing := unknown(text):
                        self.log.warning("неизвестные эмодзи: %s", ", ".join(sorted(missing)))
            for hook in self._on_load:
                await hook(app.client)
            for loop in self._loops:
                if loop.autostart:
                    loop.start()
        except BaseException:
            await self.detach()
            raise
        finally:
            current.reset(token)

    async def ready(self):
        token = current.set(self.app)
        try:
            for hook in self._on_ready:
                await hook(self.client)
        finally:
            current.reset(token)

    async def detach(self) -> None:
        if not self.loaded:
            return
        self.loaded = False
        self.app.router.remove(self)
        inline = getattr(self.app, "inline", None)
        if inline is not None:
            inline.units.remove_owner(self)
        token = current.set(self.app)
        try:
            for hook in self._on_unload:
                try:
                    await hook(self.client)
                except Exception:
                    self.log.exception("on_unload упал")
        finally:
            try:
                await self._resources.close()
            finally:
                self._app = None
                current.reset(token)

    # внутреннее

    def _guard_watcher(self, func):
        @wraps(func)
        async def handler(client, *args):
            if not self.loaded:
                return None
            # отдельная принадлежащая модулю задача: отмена не убивает воркер wzgram.
            task = self.spawn(func(client, *args))
            try:
                return await task
            except asyncio.CancelledError:
                if self.loaded:
                    raise
                return None
        return handler

    def _watcher(self, kind: type[Handler], filters: Filter | None, scope: Scope | None, *, edited: bool):
        def decorator(func: F) -> F:
            self.listens_all |= scope is None
            self._handlers.append((kind(self._guard_watcher(func), filters),
                                   (scope or Scope.ALL).default_kind(edited=edited)))
            return func
        return decorator

    def _guard_command(self, func: F) -> Callable[[Client, Message], Awaitable[None]]:
        @wraps(func)
        async def run(client: Client, message: Message) -> None:
            start = perf_counter()
            try:
                await func(client, message)
            except UserError as e:
                await self._report(message, f"{E.stop} {html.escape(str(e))}")
            except Exception as e:
                error_id = new_error_id()
                self.log.exception("команда %s сломалась", _typed(message), extra={"error_id": error_id})
                error = html.escape("".join(traceback.format_exception_only(e)).strip())
                await self._report(
                    message,
                    f"{E.stop} <b>Команда не сработала</b>\n"
                    f"Это ошибка внутри модуля {html.escape(self.name)}, а не твоя. "
                    f"Подробности записаны в лог (ошибка <code>#{error_id}</code>).\n"
                    f"<blockquote expandable>{error}</blockquote>",
                )
                return
            _commands_log.info(
                "%-16s  %-26s  %4.0f мс",
                _typed(message),
                f"в «{_chat_name(client, message)}»",
                (perf_counter() - start) * 1000,
                extra={"mark": "cmd"},
            )

        return run

    async def _report(self, message: Message, text: str) -> None:
        try:
            await respond(message, text)
        except Exception:
            self.log.exception("не удалось показать ошибку")

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._resources.tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            self.log.error("задача упала", exc_info=exc)


def _typed(message: Message) -> str:
    # команда как её написали: с префиксом и алиасом
    parts = (message.text or message.caption or "").split(None, 1)
    return parts[0] if parts else "?"


def _chat_name(client: Client, message: Message) -> str:
    chat = message.chat
    if chat is None:
        return "?"
    me = client.me
    if me is not None and chat.id == me.id:
        return "Избранное"
    return chat.full_name or str(chat.id)


def find(namespace: dict[str, Any], origin: str) -> Module:
    found = [value for value in namespace.values() if isinstance(value, Module)]
    if len(found) != 1:
        raise LoadError(f"{origin}: нужен ровно один Module, найдено {len(found)}")
    return found[0]
