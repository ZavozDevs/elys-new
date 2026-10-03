"""Module: декораторы только собирают метаданные, регистрация — в attach()."""

from __future__ import annotations

import asyncio
import html
import logging
import traceback
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from functools import wraps
from typing import Any, Protocol, TypeVar

from pyrogram import Client
from pyrogram.filters import Filter
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.handlers.handler import Handler
from pyrogram.types import Message

from elys.core.router import Command, Router
from elys.core.scope import Scope
from elys.storage.kv import KV, Namespace

from .helpers import UserError, respond

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
Hook = Callable[[Client], Awaitable[Any]]


class Host(Protocol):
    client: Client
    router: Router
    kv: KV


class LoadError(Exception):
    pass


class Module:
    def __init__(
        self,
        name: str,
        *,
        version: str = "",
        author: str = "",
        requires: Iterable[str] = (),
    ) -> None:
        self.name = name
        self.version = version
        self.author = author
        self.requires = tuple(requires)
        self.log = logging.getLogger(f"elys.mod.{name}")
        self.loaded = False
        self.app: Host | None = None
        self.client: Client | None = None
        self.db: Namespace | None = None
        self._commands: list[Command] = []
        self._handlers: list[tuple[Handler, Scope]] = []
        self._on_load: list[Hook] = []
        self._on_unload: list[Hook] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._group = 0
        self.listens_all = False  # есть вотчер без scope

    def __repr__(self) -> str:
        return f"<Module {self.name}>"

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

    def on_load(self, func: Hook) -> Hook:
        self._on_load.append(func)
        return func

    def on_unload(self, func: Hook) -> Hook:
        self._on_unload.append(func)
        return func

    # рантайм

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """фоновая задача модуля, отменяется при выгрузке."""
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
        app.router.add(*self._commands)
        self.app, self.client, self._group = app, app.client, group
        self.db = app.kv.ns(f"mod:{self.name}")
        for handler, _ in self._handlers:
            app.client.add_handler(handler, group)
        if self.listens_all:
            self.log.warning("вотчер без scope: гейт открыт для всех сообщений")
        self.loaded = True
        try:
            for hook in self._on_load:
                await hook(app.client)
        except BaseException:
            await self.detach()
            raise

    async def detach(self) -> None:
        if not self.loaded:
            return
        assert self.app is not None and self.client is not None
        self.loaded = False
        self.app.router.remove(self)  # первым: новые команды больше не стартуют
        for hook in self._on_unload:
            try:
                await hook(self.client)
            except Exception:
                self.log.exception("on_unload упал")
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for handler, _ in self._handlers:
            self.client.remove_handler(handler, self._group)

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
            try:
                await func(client, message)
            except UserError as e:
                await self._report(message, f"🚫 {e}")
            except Exception as e:
                self.log.exception("команда %s модуля %s сломалась", message.command[0], self.name)
                error = html.escape("".join(traceback.format_exception_only(e)).strip())
                await self._report(
                    message,
                    f"🚫 <b>Команда не сработала</b>\n"
                    f"Это ошибка внутри модуля {html.escape(self.name)}, а не твоя. Подробности записаны в лог.\n"
                    f"<blockquote expandable>{error}</blockquote>",
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


def find(namespace: dict[str, Any], origin: str) -> Module:
    found = [value for value in namespace.values() if isinstance(value, Module)]
    if len(found) != 1:
        raise LoadError(f"{origin}: нужен ровно один Module, найдено {len(found)}")
    return found[0]
