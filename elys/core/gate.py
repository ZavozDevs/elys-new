# гейт: отсев чужих сообщений по raw-полям, до парсинга и до сетевых запросов.

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
    # синхронный предикат на frozenset/dict; state меняется целиком присваиванием.

    __slots__ = ("listeners", "matcher", "owner_id")

    def __init__(self, listeners: Sized = (), owner_id: Callable[[], int | None] = lambda: None) -> None:
        self.listeners = listeners  # client.listeners: пока кто-то ждёт ответа — пропускаем всё
        self.matcher = Matcher()
        self.owner_id = owner_id  # id владельца; None, пока клиент не вошёл

    def _own(self, message: Any) -> bool:
        # «Избранное» приходит с out=False и без from_id, но чат — с самим владельцем: автор он.
        # Входящее от другого человека так выглядеть не может (peer_id — всегда собеседник).
        peer = getattr(message, "peer_id", None)
        return type(peer) is _PeerUser and peer.user_id == self.owner_id()

    def rebuild(self, scopes: Iterable[Scope]) -> None:
        self.matcher = Matcher(scopes)

    def __call__(self, update: Any, chats: dict, edited: bool = False) -> bool:
        message = update.message
        if getattr(message, "out", False) or self.listeners or self._own(message):
            return True
        peer = getattr(message, "peer_id", None)
        if peer is None:  # пустое сообщение
            return False
        chat_id, chat_type = _chat(peer, chats)
        return self.matcher(key(chat_type, edited=edited), chat_id)

    def short(self, update: raw.types.UpdateShortMessage | raw.types.UpdateShortChatMessage) -> bool:
        if update.out or self.listeners:
            return True
        if type(update) is _ShortMessage:
            if update.user_id == self.owner_id():  # «Избранное»
                return True
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
    # диспетчер wzgram, у которого парсеры сообщений сначала спрашивают гейт.

    def __init__(self, client: Any, gate: Gate) -> None:
        super().__init__(client)
        for types, edited in ((self.NEW_MESSAGE_UPDATES, False), (self.EDIT_MESSAGE_UPDATES, True)):
            for raw_type in types:
                self.update_parsers[raw_type] = _gated(self.update_parsers[raw_type], gate, edited)


def _gated(original: Parser, gate: Gate, edited: bool) -> Parser:
    async def parser(update: Any, users: dict, chats: dict) -> tuple[Any, type]:
        if not gate(update, chats, edited):
            return None, type(None)  # не совпадёт ни с одним хендлером, raw-хендлеры увидят
        message, handler = await original(update, users, chats)
        sender = getattr(message, "from_user", None)
        if sender is not None and sender.is_self and not message.outgoing:
            # Сообщение владельца в «Избранном» Telegram помечает входящим. Для команд, respond и
            # фильтров оно такое же своё, как отправленное в любом другом чате.
            message.outgoing = True
        return message, handler

    return parser
