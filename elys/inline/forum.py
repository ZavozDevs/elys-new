from __future__ import annotations

import contextlib
import logging
import re
from copy import deepcopy

from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    ChatAdminRequired,
    ChatWriteForbidden,
    PeerIdInvalid,
    RPCError,
    UserAlreadyParticipant,
    UserNotParticipant,
)
from pyrogram.types import ChatPrivileges

log = logging.getLogger(__name__)
TITLE = "Elys"
GENERAL = "👋 Начало"
UNAVAILABLE = (ChannelInvalid, ChannelPrivate, PeerIdInvalid, UserNotParticipant)
TOPICS = {
    "errors": ("⚠️ Ошибки", "Здесь появляются сообщения о неполадках. Подробности можно передать автору модуля. "
               "Если ошибок нет — ничего делать не нужно."),
    "updates": ("🔔 Обновления", "Здесь будут новости о новых версиях Elys. Сейчас ничего делать не нужно."),
    "backups": ("💾 Копии", "Здесь будут резервные копии и инструкции по восстановлению. "
                "Не пересылай копии другим: в них могут быть личные данные."),
}


def _plain(title):
    # Сравнение названий без эмодзи и регистра: «⚠️ Ошибки» == «ошибки».
    return re.sub(r"^[\W_]+", "", title or "").strip().casefold()


class Forum:
    def __init__(self, app):
        self.app = app
        self.state = deepcopy(app.kv.ns("core").get("forum", {}))
        self.available = False
        self.candidates = None

    async def locate(self):
        # Форумы «Elys», созданные владельцем: [(id чата, [id живых ботов-участников])]. Ничего не создаёт.
        user, found = self.app.client, []
        for chat_id in dict.fromkeys(await user.owned_forums(TITLE)):
            try:
                bots = [m.user.id async for m in user.get_chat_members(chat_id)
                        if m.user and m.user.is_bot and not m.user.is_deleted]
            except RPCError:
                bots = []
            found.append((chat_id, bots))
        self.candidates = found
        return found

    async def _adopt(self, skip=None):
        if self.candidates is None:
            await self.locate()
        candidates = [c for c in self.candidates if c[0] != skip]
        # Предпочитаем форум, где уже сидит наш бот; иначе первый найденный (последний по активности).
        candidates.sort(key=lambda c: self.app.bot.me.id not in c[1])
        if candidates:
            self.state = {"id": candidates[0][0], "topics": {}, "intros": {}}
            log.info("нашёл существующий форум Elys, использую его")
            await self._save()

    @property
    def chat_id(self):
        return self.state.get("id")

    @property
    def url(self):
        return f"https://t.me/c/{str(self.chat_id).removeprefix('-100')}/1" if self.chat_id else None

    async def _save(self):
        self.app.kv.ns("core")["forum"] = deepcopy(self.state)
        await self.app.kv.ns("core").flush()

    async def ensure(self):
        user, bot = self.app.client, self.app.bot
        skip = banned = None
        if self.chat_id:
            try:
                chat = await user.get_chat(self.chat_id)
            except UNAVAILABLE:
                skip, self.state, self.candidates = self.chat_id, {}, None
            else:
                if not chat.is_forum:
                    raise ValueError("Служебный чат больше не форум. Включи темы в его настройках и перезапусти Elys.")
                if self.state.get("installed"):
                    try:
                        status = (await user.get_chat_member(self.chat_id, bot.me.id)).status
                    except UserNotParticipant:
                        status = ChatMemberStatus.LEFT
                    if status in {ChatMemberStatus.BANNED, ChatMemberStatus.LEFT}:
                        # Форум жив, просто бота там нет: возвращаем бота, а не создаём новый форум.
                        banned = self.chat_id if status == ChatMemberStatus.BANNED else None
                        self.state = {}
        if not self.chat_id:
            await self._adopt(skip)
        if not self.chat_id:
            chat = await user.create_supergroup(TITLE, "Личный помощник: команды, настройки и уведомления",
                                                is_forum=True)
            self.state = {"id": chat.id, "topics": {}, "intros": {}}
            await self._save()
        if not self.state.get("installed"):
            if banned == self.chat_id:
                await user.unban_chat_member(self.chat_id, bot.me.id)
            with contextlib.suppress(UserAlreadyParticipant):
                await user.add_chat_members(self.chat_id, bot.me.username)
        await user.promote_chat_member(self.chat_id, bot.me.username, privileges=ChatPrivileges(
            can_manage_topics=True, can_pin_messages=True, can_delete_messages=True, can_change_info=True,
        ))
        self.state["installed"] = True
        await self._save()
        # Получение чата ботом проверяет доступ и прогревает его peer-кэш.
        await bot.get_chat(self.chat_id)
        existing = {topic.id: topic.title async for topic in user.get_forum_topics(self.chat_id)}
        if not self.state.get("general_named"):
            if existing.get(1) != GENERAL:
                await bot.edit_general_forum_topic(self.chat_id, GENERAL)
            self.state["general_named"] = True
            await self._save()
        for key, (title, intro) in TOPICS.items():
            topic_id = self.state["topics"].get(key)
            if topic_id not in existing:
                # Темы ищем по названию: форум могли подхватить, а сохранённые id — потеряться.
                topic_id = next((i for i, name in existing.items() if i != 1 and _plain(name) == _plain(title)), None)
                if topic_id is None:
                    topic_id = (await bot.create_forum_topic(self.chat_id, title)).id
                self.state["topics"][key] = topic_id
                self.state["intros"].pop(key, None)
                await self._save()
            if key not in self.state["intros"]:
                message = await self._find_intro(topic_id, intro) or await bot.send_message(
                    self.chat_id, intro, message_thread_id=topic_id, disable_notification=True)
                self.state["intros"][key] = message.id
                await self._save()
            pinned = self.state.setdefault("pinned", {})
            if pinned.get(key) != self.state["intros"][key]:
                await bot.pin_chat_message(self.chat_id, self.state["intros"][key], disable_notification=True)
                pinned[key] = self.state["intros"][key]
                await self._save()
        self.available = True
        return self

    async def _find_intro(self, topic_id, intro):
        # Вводное сообщение могло остаться в подхваченной теме: не дублируем его.
        try:
            async for message in self.app.client.search_messages(self.chat_id, query=intro[:40],
                                                                 top_msg_id=topic_id, limit=5):
                if (message.text or "").startswith(intro[:40]):
                    return message
        except Exception as error:  # поиск необязателен: при сбое парсера wzgram просто пришлём вводное заново
            log.warning("не удалось проверить вводное сообщение темы: %s", error)
        return None

    async def is_private(self):
        # Секреты нельзя спрашивать в группе, куда владелец добавил других людей. Удалённые аккаунты
        # (например, прежний бот подхваченного форума) не считаются.
        members = [m async for m in self.app.client.get_chat_members(self.chat_id)]
        people = {m.user.id for m in members if not getattr(m.user, "is_deleted", False)}
        return people == {self.app.client.me.id, self.app.bot.me.id}

    async def send(self, topic, text, **kwargs):
        if self.available:
            try:
                return await self.app.bot.send_message(
                    self.chat_id, text, message_thread_id=self.state["topics"].get(topic),
                    disable_notification=topic != "updates", **kwargs,
                )
            except (*UNAVAILABLE, ChatWriteForbidden, ChatAdminRequired):
                self.available = False
        return await self.app.bot_service.send_private(text, disable_notification=True, **kwargs)
