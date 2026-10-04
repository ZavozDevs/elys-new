"""гейт: отсев чужих сообщений по raw-полям, до парсинга и до сетевых запросов."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sized
from typing import Any

from pyrogram import raw
from pyrogram.dispatcher import Dispatcher

from .scope import CHANNEL, GROUP, PRIVATE, Matcher, Scope, key

_PeerUser = raw.types.PeerUser
_PeerChat = raw.types.PeerChat
_ShortMessage = raw.types.UpdateShortMessage
_CHANNEL_BASE = -1_000_000_000_000  # id канала в bot api: -100… (как utils.get_channel_id)

Parser = Callable[[Any, dict, dict], Awaitable[tuple[Any, type]]]


class Gate:
    """синхронный предикат на frozenset/dict; state меняется целиком присваиванием."""

    __slots__ = ("listeners", "matcher")

    def __init__(self, listeners: Sized = ()) -> None:
        self.listeners = listeners  # client.listeners: пока кто-то ждёт ответа — пропускаем всё
        self.matcher = Matcher()

    def rebuild(self, scopes: Iterable[Scope]) -> None:
        self.matcher = Matcher(scopes)

    def __call__(self, update: Any, chats: dict, edited: bool = False) -> bool:
        message = update.message
        if getattr(message, "out", False) or self.listeners:
            return True
        peer = getattr(message, "peer_id", None)
        if peer is None:  # MessageEmpty
            return False
        chat_id, chat_type = _chat(peer, chats)
        return self.matcher(key(chat_type, edited=edited), chat_id)

    def short(self, update: raw.types.UpdateShortMessage | raw.types.UpdateShortChatMessage) -> bool:
        if update.out or self.listeners:
            return True
        if type(update) is _ShortMessage:
            chat_id, chat_type = update.user_id, PRIVATE
        else:
            chat_id, chat_type = -update.chat_id, GROUP
        return self.matcher(key(chat_type), chat_id)


def _chat(peer: Any, chats: dict) -> tuple[int, int]:
    cls = type(peer)
    if cls is _PeerUser:
        return peer.user_id, PRIVATE
    if cls is _PeerChat:
        return -peer.chat_id, GROUP
    channel = chats.get(peer.channel_id)
    chat_type = CHANNEL if getattr(channel, "broadcast", False) else GROUP
    return _CHANNEL_BASE - peer.channel_id, chat_type


class GateDispatcher(Dispatcher):
    """диспетчер wzgram, у которого парсеры сообщений сначала спрашивают гейт."""

    def __init__(self, client: Any, gate: Gate) -> None:
        super().__init__(client)
        for types, edited in ((self.NEW_MESSAGE_UPDATES, False), (self.EDIT_MESSAGE_UPDATES, True)):
            for raw_type in types:
                self.update_parsers[raw_type] = _gated(self.update_parsers[raw_type], gate, edited)


def _gated(original: Parser, gate: Gate, edited: bool) -> Parser:
    async def parser(update: Any, users: dict, chats: dict) -> tuple[Any, type]:
        if not gate(update, chats, edited):
            return None, type(None)  # не совпадёт ни с одним хендлером, raw-хендлеры увидят
        return await original(update, users, chats)

    return parser
