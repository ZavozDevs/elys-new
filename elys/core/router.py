"""роутер команд: префикс → dict-поиск → проверка прав → задача владельца."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from pyrogram import Client
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.types import Message

GROUP = -1000

# разбор аргументов как в filters.command: кавычки группируют
_ARGS = re.compile(r"([\"'])(.*?)(?<!\\)\1|(\S+)")
_UNQUOTE = re.compile(r"\\([\"'])")


class Owner(Protocol):
    name: str

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> Any: ...


@dataclass(frozen=True, slots=True, eq=False)
class Command:
    name: str
    callback: Callable[[Client, Message], Awaitable[Any]]
    owner: Owner
    aliases: tuple[str, ...] = ()
    roles: frozenset[str] = frozenset()

    @property
    def names(self) -> tuple[str, ...]:
        return self.name, *self.aliases


class CommandConflict(Exception):
    def __init__(self, name: str, owner: str) -> None:
        super().__init__(f"команда {name!r} уже занята модулем {owner}")
        self.name, self.owner = name, owner


Allow = Callable[[Message, Command], bool]


def owner_only(message: Message, command: Command) -> bool:
    return bool(message.outgoing)


class Router:
    def __init__(self, prefixes: Iterable[str], allow: Allow = owner_only) -> None:
        self._commands: dict[str, Command] = {}
        self.allow = allow
        self.prefixes = prefixes

    @property
    def prefixes(self) -> tuple[str, ...]:
        return self._prefixes

    @prefixes.setter
    def prefixes(self, value: Iterable[str]) -> None:
        prefixes = tuple(sorted(set(value), key=len, reverse=True))  # длинный префикс раньше
        if not prefixes or not all(p and not p[0].isspace() for p in prefixes):
            raise ValueError(f"плохие префиксы: {prefixes!r}")
        self._prefixes = prefixes
        self._first = frozenset(p[0] for p in prefixes)

    def add(self, *commands: Command, force: bool = False) -> None:
        # всё или ничего: конфликт не оставляет половину команд
        if not force:
            for command in commands:
                for name in command.names:
                    other = self._commands.get(name)
                    if other is not None and other.owner is not command.owner:
                        raise CommandConflict(name, other.owner.name)
        for command in commands:
            for name in command.names:
                self._commands[name] = command

    def remove(self, owner: Owner) -> None:
        self._commands = {n: c for n, c in self._commands.items() if c.owner is not owner}

    def get(self, name: str) -> Command | None:
        return self._commands.get(name.lower())

    def handlers(self) -> tuple[MessageHandler, EditedMessageHandler]:
        return MessageHandler(self.dispatch), EditedMessageHandler(self.dispatch)

    async def dispatch(self, client: Client, message: Message) -> None:
        # без await до spawn: выгрузка модуля не может вклиниться между поиском и запуском
        text = message.text or message.caption
        if not text or text[0] not in self._first:
            return
        prefix = next((p for p in self._prefixes if text.startswith(p)), None)
        if prefix is None:
            return
        body = text[len(prefix) :]
        if not body or body[0].isspace():
            return
        name, *rest = body.split(None, 1)
        command = self._commands.get(name.lower())
        if command is None or not self.allow(message, command):
            return
        message.command = [command.name, *parse_args(rest[0] if rest else "")]
        command.owner.spawn(command.callback(client, message))


def parse_args(text: str) -> list[str]:
    return [_UNQUOTE.sub(r"\1", m[2] or m[3] or "") for m in _ARGS.finditer(text)]
