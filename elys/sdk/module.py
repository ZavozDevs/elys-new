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
from pyrogram.filters import Filter
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.handlers.handler import Handler
from pyrogram.types import Message

from elys.core.router import Command, Router
from elys.core.scope import Scope
from elys.log import new_error_id
from elys.storage.kv import KV, Namespace

from .helpers import UserError, respond

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
Hook = Callable[[Client], Awaitable[Any]]

_commands_log = logging.getLogger("elys.cmd")  # строка ▸ на каждую выполненную команду


class Host(Protocol):
    client: Client
    router: Router
    kv: KV


class LoadError(Exception):
    pass


class Module:
    def __init__(self, name: str) -> None:
        self.name = name
        self.log = logging.getLogger(f"elys.mod.{name}")
        self.loaded = False
        self._app: Host | None = None
        self._registered: list[Handler] = []
        self._commands: list[Command] = []
        self._handlers: list[tuple[Handler, Scope]] = []
        self._on_load: list[Hook] = []
        self._on_unload: list[Hook] = []
        self._tasks: set[asyncio.Task[Any]] = set()
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

    # декораторы

    def command(self, name: str, *, aliases: Iterable[str] = ()) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            self._commands.append(
                Command(
                    name.lower(),
                    self._guard_command(func),
                    self,
                    tuple(a.lower() for a in aliases),
                )
            )
            return func

        return decorator

    def on_message(self, filters: Filter | None = None, *, scope: Scope | None = None) -> Callable[[F], F]:
        return self._watcher(MessageHandler, filters, scope, edited=False)

    def on_edited_message(self, filters: Filter | None = None, *, scope: Scope | None = None) -> Callable[[F], F]:
        return self._watcher(EditedMessageHandler, filters, scope, edited=True)

    def on_load(self, func: Hook) -> Hook:
        self._on_load.append(func)
        return func

    def on_unload(self, func: Hook) -> Hook:
        self._on_unload.append(func)
        return func

    # рантайм

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        # фоновая задача модуля, отменяется при выгрузке.
        if not self.loaded:
            coro.close()
            raise RuntimeError(f"{self.name} не загружен")
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    @property
    def scopes(self) -> list[Scope]:
        return [scope for _, scope in self._handlers]

    async def attach(self, app: Host, group: int) -> None:
        if self._app is not None:
            raise RuntimeError(f"{self.name} уже загружен")
        app.router.add(*self._commands)
        self._app, self._group = app, group
        self.loaded = True
        try:
            for handler, _ in self._handlers:
                app.client.add_handler(handler, group)
                self._registered.append(handler)
            if self.listens_all:
                self.log.warning("вотчер без scope: гейт открыт для всех сообщений")
            for hook in self._on_load:
                await hook(app.client)
        except BaseException:
            await self.detach()
            raise

    async def detach(self) -> None:
        if not self.loaded:
            return
        self.loaded = False
        self.app.router.remove(self)  # первым: новые команды больше не стартуют
        try:
            for hook in self._on_unload:
                try:
                    await hook(self.client)
                except Exception:
                    self.log.exception("on_unload упал")
        finally:
            try:
                tasks = tuple(self._tasks)
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                for handler in self._registered:
                    self.client.remove_handler(handler, self._group)
                self._registered.clear()
                self._app = None

    # внутреннее

    def _watcher(self, kind: type[Handler], filters: Filter | None, scope: Scope | None, *, edited: bool):
        def decorator(func: F) -> F:
            @wraps(func)
            async def handler(client: Client, update: Any) -> Any:
                # remove_handler асинхронный: апдейт может прийти уже после выгрузки
                if self.loaded:
                    return await func(client, update)
                return None

            self.listens_all |= scope is None
            self._handlers.append((kind(handler, filters), (scope or Scope.ALL).default_kind(edited=edited)))
            return func

        return decorator

    def _guard_command(self, func: F) -> Callable[[Client, Message], Awaitable[None]]:
        @wraps(func)
        async def run(client: Client, message: Message) -> None:
            start = perf_counter()
            try:
                await func(client, message)
            except UserError as e:
                await self._report(message, f"🚫 {html.escape(str(e))}")
            except Exception as e:
                error_id = new_error_id()
                self.log.exception("команда %s сломалась", _typed(message), extra={"error_id": error_id})
                error = html.escape("".join(traceback.format_exception_only(e)).strip())
                await self._report(
                    message,
                    f"🚫 <b>Команда не сработала</b>\n"
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
        self._tasks.discard(task)
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
