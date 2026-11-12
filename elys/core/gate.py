# гейт: отсев чужих сообщений по raw-полям, до парсинга и до сетевых запросов.

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sized
from time import time
from typing import Any

from pyrogram import raw
from pyrogram.dispatcher import Dispatcher

from .scope import CHANNEL, GROUP, PRIVATE, Matcher, Scope, key

_PeerUser = raw.types.PeerUser
_PeerChat = raw.types.PeerChat
_ShortMessage = raw.types.UpdateShortMessage
_CHANNEL_BASE = -1_000_000_000_000  # id канала в bot api: -100… (как utils.get_channel_id)
_STALE = 60  # с: edit со старым edit_date — не правка, а реакция/превью на старом сообщении (§4.2)

Parser = Callable[[Any, dict, dict], Awaitable[tuple[Any, type]]]


class Gate:
    # синхронный предикат на frozenset/dict; state меняется целиком присваиванием.

    __slots__ = ("listeners", "matcher", "owner_id", "trusted")

    def __init__(self, listeners: Sized = (), owner_id: Callable[[], int | None] = lambda: None) -> None:
        self.listeners = listeners  # client.listeners: пока кто-то ждёт ответа — пропускаем всё
        self.matcher = Matcher()
        self.owner_id = owner_id  # id владельца; None, пока клиент не вошёл
        self.trusted: frozenset[int] = frozenset()  # security.trusted_ids: люди и чаты с доступом к командам

    def _own(self, message: Any) -> bool:
        # «Избранное» приходит с out=False и без from_id, но чат — с самим владельцем: автор он.
        # Входящее от другого человека так выглядеть не может (peer_id — всегда собеседник).
        peer = getattr(message, "peer_id", None)
        return type(peer) is _PeerUser and peer.user_id == self.owner_id()

    def rebuild(self, scopes: Iterable[Scope]) -> None:
        self.matcher = Matcher(scopes)

    def __call__(self, update: Any, chats: dict, edited: bool = False) -> bool:
        message = update.message
        if edited and _stale(message):  # до out: повтор опасен как раз для своих команд
            return False
        if getattr(message, "out", False) or self.listeners or self._own(message):
            return True
        peer = getattr(message, "peer_id", None)
        if peer is None:  # пустое сообщение
            return False
        chat_id, chat_type = _chat(peer, chats)
        sender = getattr(message, "from_id", None)  # отправитель: from_id or peer_id
        if chat_id in self.trusted or (sender is not None and _chat(sender, chats)[0] in self.trusted):
            return True
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
            if update.from_id in self.trusted:
                return True
        if chat_id in self.trusted:
            return True
        return self.matcher(key(chat_type), chat_id)


def _stale(message: Any) -> bool:
    # реакции, превью ссылки и правки инлайн-ботом приходят как edit, но edit_date не двигают (или прячут его
    # через edit_hide): без отсева старое «.t …» выполнилось бы снова. У ephemeral edit_date нет — пропускаем.
    now = time()
    return bool(getattr(message, "edit_hide", False)) or (getattr(message, "edit_date", now) or 0) < now - _STALE


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
                self.update_parsers[raw_type] = _gated(self.update_parsers[raw_type], gate, edited, client)


def _gated(original: Parser, gate: Gate, edited: bool, client: Any) -> Parser:
    async def parser(update: Any, users: dict, chats: dict) -> tuple[Any, type]:
        if not gate(update, chats, edited):
            message = update.message
            if edited and getattr(message, "peer_id", None) is not None:
                # Правка мимо парсера: кэш wzgram хранил бы старый текст, и reply_to_message / get_reply
                # (r в .e) отдавали бы сообщение до правки. Забываем — следующий ответ загрузит свежее.
                client.message_cache.pop((_chat(message.peer_id, chats)[0], message.id), None)
            return None, type(None)  # не совпадёт ни с одним хендлером, raw-хендлеры увидят
        message, handler = await original(update, users, chats)
        sender = getattr(message, "from_user", None)
        if sender is not None and sender.is_self and not message.outgoing:
            # Сообщение владельца в «Избранном» Telegram помечает входящим. Для команд, respond и
            # фильтров оно такое же своё, как отправленное в любом другом чате.
            message.outgoing = True
        return message, handler

    return parser
