from __future__ import annotations

import asyncio
import logging
import re
import secrets

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import (
    AccessTokenExpired,
    AccessTokenInvalid,
    InputUserDeactivated,
    PeerIdInvalid,
    RPCError,
    UserDeactivated,
    UserIsBlocked,
)
from pyrogram.handlers import MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from elys.core.registry import change_handler
from elys.storage.files import private_directory, protect_existing
from elys.storage.sqlite import SafeSQLiteStorage

from .botfather import BOT_TITLE, BotFatherWebApp, BotSetupError, create_bot_in_chat

log = logging.getLogger(__name__)
GROUP = -1100


class _StaleBot(Exception):
    # args: (сообщение для владельца, токен недействителен)
    pass


class BotClient(Client):
    async def authorize(self):
        # Не запускаем интерактивный мастер wzgram и не печатаем токен.
        return await self.sign_in_bot(self.bot_token)

    async def start(self):
        try:
            return await super().start()
        except BaseException:
            if self.is_connected:
                await self.disconnect()
            raise
        finally:
            protect_existing(self.storage.database)


class BotService:
    def __init__(self, app):
        self.app = app
        self.client = None
        self._probe = None
        self._verify_lock = asyncio.Lock()
        self._handler = MessageHandler(self._private, filters.private & filters.incoming)

    async def _discover(self, father):
        # Ищем уже существующего бота по списку Web App BotFather, чтобы не создавать нового:
        # сохранённый username, затем бот, созданный Elys (по шаблону username или названию).
        bots = await father.bots()
        saved = (self.app.kv.ns("core").get("bot_username") or "").lower()
        if saved in bots:
            return saved, bots[saved][0]
        own = re.compile(rf"elys_{self.app.client.me.id}_[0-9a-f]{{6}}_bot")
        for name, (identity, title) in bots.items():
            if own.fullmatch(name) or title == BOT_TITLE:
                return name, identity
        return None

    async def _provision(self):
        core = self.app.kv.ns("core")
        if core.get("bot_token") and core.get("bot_inline_token") == core.get("bot_feedback") == core["bot_token"]:
            return core["bot_token"]
        try:
            link = await asyncio.wait_for(self.app.client.get_main_web_app("BotFather", "BotFather"), timeout=20)
        except (RPCError, TimeoutError, OSError):
            raise BotSetupError("Не удалось открыть Web App BotFather. Проверь Telegram и перезапусти Elys.") from None
        father = BotFatherWebApp(link)
        await father.authenticate()
        if not core.get("bot_token"):
            token = None
            identity = core.get("bot_id")
            if not identity:
                found = await self._discover(father)
                if found:
                    core["bot_username"], identity = found
                    log.info("нашёл существующего бота-помощника @%s", found[0])
            if not identity:
                username = core.get("bot_username")
                if not username:
                    username = f"elys_{self.app.client.me.id}_{secrets.token_hex(3)}_bot"
                    # Сохраняем до запроса: даже при потерянном ответе createBot найдём того же бота.
                    core["bot_username"] = username
                    await core.flush()
                log.info("создаю бота-помощника через Web App @BotFather…")
                try:
                    identity = await father.create_bot(username)
                except BotSetupError:
                    # Web App мог создать бота, но потерять ответ; иначе — запасной путь через /newbot.
                    identity = await father.find_bot(username)
                    if not identity:
                        log.warning("Web App не создал бота, создаю через чат с @BotFather (/newbot)")
                        token = await create_bot_in_chat(self.app.client, username)
                        identity = int(token.split(":", 1)[0])
            core["bot_id"] = identity
            await core.flush()
            core["bot_token"] = token or await father.token(identity)
            await core.flush()
        identity = int(core["bot_token"].split(":", 1)[0])
        await father.enable_inline(identity)
        core["bot_inline_token"] = core["bot_feedback"] = core["bot_token"]
        await core.flush()
        return core["bot_token"]

    async def start(self):
        settings = self.app.settings
        private_directory(settings.data_dir)
        for path in settings.data_dir.glob("bot.session*"):
            protect_existing(path)
        for attempt in range(2):
            token = await self._provision()
            try:
                return await self._connect(token)
            except _StaleBot as stale:
                if attempt:
                    raise BotSetupError(stale.args[0]) from None
                # Бота удалили или токен отозвали: ищем бота заново, а не создаём сразу нового.
                log.warning("данные бота-помощника устарели, ищу бота заново")
                await self._forget(token_dead=stale.args[1])

    async def _forget(self, *, token_dead):
        core = self.app.kv.ns("core")
        if token_dead:
            for key in ("bot_token", "bot_inline_token", "bot_feedback", "bot_id", "bot_username", "bot_verified"):
                core.pop(key, None)
            await core.flush()
        # Сессию не удаляем, а откладываем в сторону: она принадлежит другому боту или недействительна.
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = self.app.settings.data_dir / f"bot.session{suffix}"
            if path.exists():
                path.replace(path.with_name(path.name + ".old"))

    async def _connect(self, token):
        settings = self.app.settings
        self.client = BotClient(
            "bot", api_id=settings.api_id, api_hash=settings.api_hash, bot_token=token,
            workdir=settings.data_dir, parse_mode=ParseMode.HTML, skip_updates=True,
            storage_engine=SafeSQLiteStorage("bot", workdir=settings.data_dir),
            fetch_replies=False, fetch_topics=False, fetch_stories=False, fetch_stickers=False,
            auto_no_updates=True, rate_limits=settings.rate_limits,
        )
        try:
            try:
                await self.client.start()
            except (AccessTokenExpired, AccessTokenInvalid, UserDeactivated):
                # Удалённый бот отвечает на GetState как USER_DEACTIVATED, а не ACCESS_TOKEN_INVALID.
                raise _StaleBot("Telegram не принимает токен бота-помощника. Проверь в @BotFather, "
                                "что бот существует. Нужна повторная настройка доступа к боту.", True) from None
            if not self.client.me.is_bot or self.client.me.id != int(token.split(":", 1)[0]):
                raise _StaleBot("Сохранённая сессия принадлежит другому боту. Останови Elys и "
                                "перемести data/bot.session в резервную копию, затем запусти снова.", False)
            self.app.bot = self.client
            await change_handler(self.client, self._handler, GROUP)
            core = self.app.kv.ns("core")
            if core.get("bot_verified") != self.client.me.id:
                await self.verify()
            return self.client
        except BaseException:
            if self.client.is_initialized:
                await self.client.stop()
            self.app.bot = None
            raise

    async def stop(self):
        if self.client is not None:
            try:
                await self.client.stop()
            finally:
                protect_existing(self.client.storage.database)
                self.app.bot = None

    async def verify(self):
        async with self._verify_lock:
            user = self.app.client
            await user.unblock_user(self.client.me.username)
            # Обновляет peer-кэш юзербота до отправки.
            await user.get_users(self.client.me.username)
            self._probe = asyncio.get_running_loop().create_future()
            sent = reply = None
            try:
                sent = await user.send_message(self.client.me.username, "/start")
                reply = await asyncio.wait_for(self._probe, timeout=10)
            except TimeoutError:
                raise BotSetupError("Бот не ответил за 10 секунд. Проверь, что он не заблокирован, "
                                    "и перезапусти Elys; кнопки пока недоступны.") from None
            finally:
                self._probe = None
                ids = [m.id for m in (sent, reply) if m is not None]
                if ids:
                    await user.delete_messages(self.client.me.username, ids, revoke=True)
            self.app.kv.ns("core")["bot_verified"] = self.client.me.id
            await self.app.kv.ns("core").flush()

    async def _private(self, bot, message):
        if not message.from_user or message.from_user.id != self.app.client.me.id:
            return
        forum = getattr(self.app, "forum", None)
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть Elys", url=forum.url)]]) \
            if forum and forum.url else None
        text = "Я помощник Elys. Всё — в чате «Elys»." if markup else "Я помощник Elys. Чат «Elys» сейчас создаётся."
        reply = await bot.send_message(message.chat.id, text, reply_markup=markup, disable_notification=True)
        if (message.text or "").split() == ["/start"] and self._probe and not self._probe.done():
            self._probe.set_result(reply)

    async def send_private(self, text, **kwargs):
        for attempt in range(2):
            try:
                return await self.client.send_message(self.app.client.me.id, text, **kwargs)
            except (UserIsBlocked, PeerIdInvalid, InputUserDeactivated):
                if attempt == 0:
                    try:
                        await self.verify()
                    except Exception:
                        break
        log.error("Не удалось доставить важное сообщение в Telegram: %s", text,
                  extra={"no_telegram": True})
        return None
