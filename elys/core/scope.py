"""scope: какие raw-сообщения нужны вотчеру — гейт проверяет это до парсинга."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import product
from typing import ClassVar

# тип чата
PRIVATE, GROUP, CHANNEL = 0, 1, 2


def key(chat_type: int, *, out: bool = False, edited: bool = False) -> int:
    # ключ апдейта: вид | направление | тип чата
    return edited << 3 | out << 2 | chat_type


@dataclass(frozen=True, slots=True, kw_only=True)
class Scope:
    """маска по категориям: внутри категории «или», между категориями «и», 0 — любые."""

    kinds: int = 0
    directions: int = 0
    chat_types: int = 0
    chat_ids: frozenset[int] | None = None

    INCOMING: ClassVar[Scope]
    OUTGOING: ClassVar[Scope]
    PRIVATE: ClassVar[Scope]
    GROUP: ClassVar[Scope]
    CHANNEL: ClassVar[Scope]
    EDITED: ClassVar[Scope]
    ALL: ClassVar[Scope]

    @staticmethod
    def chats(ids: Iterable[int]) -> Scope:
        return Scope(chat_ids=frozenset(ids))

    def __or__(self, other: Scope) -> Scope:
        if self.chat_ids is None or other.chat_ids is None:
            chat_ids = self.chat_ids if other.chat_ids is None else other.chat_ids
        else:
            chat_ids = self.chat_ids | other.chat_ids
        return Scope(
            kinds=self.kinds | other.kinds,
            directions=self.directions | other.directions,
            chat_types=self.chat_types | other.chat_types,
            chat_ids=chat_ids,
        )

    def default_kind(self, *, edited: bool) -> Scope:
        # вид по типу хендлера, если не задан явно
        if self.kinds:
            return self
        return Scope(
            kinds=1 << edited,
            directions=self.directions,
            chat_types=self.chat_types,
            chat_ids=self.chat_ids,
        )

    def keys(self) -> frozenset[int]:
        return frozenset(
            key(t, out=bool(d), edited=bool(k))
            for k, d, t in product(_bits(self.kinds, 2), _bits(self.directions, 2), _bits(self.chat_types, 3))
        )


def _bits(mask: int, size: int) -> tuple[int, ...]:
    return tuple(i for i in range(size) if not mask or mask >> i & 1)


Scope.INCOMING = Scope(directions=1 << 0)
Scope.OUTGOING = Scope(directions=1 << 1)
Scope.PRIVATE = Scope(chat_types=1 << PRIVATE)
Scope.GROUP = Scope(chat_types=1 << GROUP)
Scope.CHANNEL = Scope(chat_types=1 << CHANNEL)
Scope.EDITED = Scope(kinds=1 << 1)
Scope.ALL = Scope()


class Matcher:
    """сводный scope всех вотчеров: проверка — один-два поиска в frozenset."""

    __slots__ = ("any_chat", "by_chat")

    def __init__(self, scopes: Iterable[Scope] = ()) -> None:
        any_chat: set[int] = set()
        by_chat: dict[int, set[int]] = {}
        for scope in scopes:
            keys = scope.keys()
            if scope.chat_ids is None:
                any_chat |= keys
            else:
                for chat_id in scope.chat_ids:
                    by_chat.setdefault(chat_id, set()).update(keys)
        self.any_chat = frozenset(any_chat)
        self.by_chat = {chat_id: frozenset(keys) for chat_id, keys in by_chat.items()}

    def __call__(self, key: int, chat_id: int) -> bool:
        if key in self.any_chat:
            return True
        keys = self.by_chat.get(chat_id)
        return keys is not None and key in keys

    def __bool__(self) -> bool:
        return bool(self.any_chat or self.by_chat)
