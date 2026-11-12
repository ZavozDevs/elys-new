from __future__ import annotations

import asyncio
import logging
import re
from contextlib import suppress

from pyrogram import StopPropagation, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified, QueryIdInvalid, RPCError
from pyrogram.handlers import CallbackQueryHandler, ChosenInlineResultHandler, InlineQueryHandler
from pyrogram.raw.types import (
    Updates,
    UpdatesCombined,
    UpdateShortChatMessage,
    UpdateShortMessage,
    UpdateShortSentMessage,
)
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputMediaPhoto,
    InputTextMessageContent,
)

from elys.core.registry import change_handler
from elys.i18n import catalog
from elys.ui.banner import preview
from elys.ui.emoji import PLACEHOLDER, render

from .list import close_button, page_buttons
from .units import Units

log = logging.getLogger(__name__)
GROUP = -1000
_CALLBACK = re.compile(r"^([A-Za-z0-9]{8}):(\d+)$")


def _extract_msg_id(res):
    if res is None:
        return None
    if isinstance(res, (UpdateShortSentMessage, UpdateShortMessage, UpdateShortChatMessage)):
        return res.id
    if isinstance(res, (Updates, UpdatesCombined)):
        for u in getattr(res, "updates", ()):
            mid = getattr(getattr(u, "message", None), "id", None)
            if isinstance(mid, int):
                return mid
            if hasattr(u, "id") and isinstance(u.id, int):
                return u.id
    return getattr(res, "id", None) if isinstance(getattr(res, "id", None), int) else None


class Inline:
    def __init__(self, app):
        self.app = app
        self.units = Units()
        self._cleaner = None
        self._handlers = []

    async def start(self):
        async def unit_query(_, client, query):
            return query.query.startswith("elys:")

        async def unit_callback(_, client, query):
            return isinstance(query.data, str) and bool(_CALLBACK.fullmatch(query.data))

        async def unit_chosen(_, client, result):
            return self.units.get(getattr(result, "result_id", None)) is not None

        handlers = [
            InlineQueryHandler(self._query, filters.create(unit_query)),
            CallbackQueryHandler(self._callback, filters.create(unit_callback)),
            ChosenInlineResultHandler(self._chosen, filters.create(unit_chosen)),
        ]
        for handler in handlers:
            await change_handler(self.app.bot, handler, GROUP)
            self._handlers.append(handler)
        self._cleaner = asyncio.create_task(self.units.clean())

    async def close(self):
        if self._cleaner:
            self._cleaner.cancel()
            with suppress(asyncio.CancelledError):
                await self._cleaner
        self.units.clear()
        for handler in reversed(self._handlers):
            await change_handler(self.app.bot, handler, GROUP, remove=True)
        self._handlers.clear()

    def _keyboard(self, unit, rows):
        buttons, keyboard = {}, []
        for row in rows:
            rendered = []
            for button in row:
                index = unit.next_button
                unit.next_button += 1
                rendered.append(
                    button.render(f"{unit.id}:{index}", premium=self.app.premium, direct=unit.data.get("direct", False))
                )
                if button.callback or button.query is not None:
                    buttons[index] = button
            if rendered:
                keyboard.append(rendered)
        unit.buttons = buttons
        return InlineKeyboardMarkup(keyboard) if keyboard else None

    def _text(self, text):
        return render(text, self.app.premium)

    def _t(self, key):
        app = self.app
        return (getattr(app, "i18n", None) or catalog).t(f"form.{key}", language=getattr(app, "language", "ru"))

    def _rich(self, rich):
        # rich заменяет текст целиком; бот шлёт его и без Premium. Режим «off» — только обычный текст.
        if not rich or self.app.rich == "off":
            return {}
        return {"rich_text": self._text(rich), "rich_text_parse_mode": ParseMode.HTML}

    def deferred(self, text, rich=None):
        # Ни премиум-эмодзи, ни rich нельзя отправить в inline-результате: отправляем заглушку, затем бот правит.
        # Нужен Inline Feedback (флаг bot_feedback ставит BotService), иначе inline_message_id не узнать.
        core = self.app.kv.ns("core")
        return bool(
            core.get("bot_feedback")
            and core.get("bot_feedback") == core.get("bot_token")
            and (self._rich(rich) or (self.app.premium and "<tg-emoji" in self._text(text)))
        )

    async def form(
        self,
        owner,
        message,
        text,
        buttons=(),
        *,
        banner=None,
        rich=None,
        allowed_ids=None,
        ttl=86400,
        kind="form",
        data=None,
    ):
        if not owner.loaded:
            raise RuntimeError("модуль уже выключен")
        if allowed_ids is None:  # кнопки — владельцу и тому, кто вызвал команду (sudo)
            sender = getattr(message, "from_user", None)
            allowed_ids = {self.app.client.me.id, *([sender.id] if sender else [])}
        unit = self.units.add(
            owner, kind, {"text": text, "rich": rich, "banner": banner, **(data or {})}, allowed_ids, ttl=ttl
        )
        try:
            if self.deferred(text, rich):
                unit.data["sent"] = asyncio.get_running_loop().create_future()
            rows = list(buttons) or [[close_button(self._dismiss)]]
            unit.data["markup"] = self._keyboard(unit, rows)
            results = await self.app.client.get_inline_bot_results(self.app.bot.me.username, f"elys:{unit.id}")
            if not results.results:
                raise RuntimeError("Бот не вернул форму. Перезапусти Elys и попробуй снова.")
            chat_id = message if isinstance(message, int) else message.chat.id
            unit.data["chat_id"] = chat_id
            sent_raw = await self.app.client.send_inline_bot_result(
                chat_id, results.query_id, unit.id, message_thread_id=getattr(message, "message_thread_id", None)
            )
            msg_id = _extract_msg_id(sent_raw)
            if msg_id:
                unit.data["message_id"] = msg_id
            if "sent" in unit.data:
                await self._finish(unit)
            return unit
        except BaseException:
            self.units.remove(unit.id)
            raise

    async def _chosen(self, bot, result):
        unit = self.units.get(getattr(result, "result_id", None))
        if unit:
            if getattr(result, "inline_message_id", None):
                unit.data["inline_message_id"] = result.inline_message_id
            sent = unit.data.get("sent")
            if sent and not sent.done() and getattr(result, "inline_message_id", None):
                sent.set_result(result.inline_message_id)
        raise StopPropagation

    async def _finish(self, unit):
        # Заменяем заглушку полным текстом. Пауза не нужна: правка сразу после выбора проходит
        # (проверено на живом аккаунте); повторы — только на случай временной ошибки.
        try:
            inline_id = await asyncio.wait_for(unit.data["sent"], 10)
        except TimeoutError:
            log.warning(
                "Telegram не сообщил о выбранной форме, полный текст не показан. "
                "Проверь Inline Feedback бота в @BotFather."
            )
            return
        finally:
            unit.data.pop("sent", None)  # дальше форма обычная: повторный запрос получит полный текст
        for attempt in range(4):
            try:
                if unit.kind == "gallery":
                    await self.app.bot.edit_inline_caption(
                        inline_id,
                        self._text(unit.data["text"]),
                        parse_mode=ParseMode.HTML,
                        reply_markup=unit.data["markup"],
                    )
                else:
                    await self.app.bot.edit_inline_text(
                        inline_id,
                        self._text(unit.data["text"]),
                        parse_mode=ParseMode.HTML,
                        reply_markup=unit.data["markup"],
                        **self._rich(unit.data.get("rich")),
                        link_preview_options=preview(unit.data["banner"], self.app.banners_enabled),
                    )
                return
            except MessageNotModified:
                return
            except RPCError:
                if attempt == 3:
                    log.exception("Не удалось показать полный текст формы")
                    return
                await asyncio.sleep(0.1 * 2**attempt)

    async def bot_form(self, owner, chat_id, text, buttons=(), *, rich=None, ttl=86400, thread=None):
        if not owner.loaded:
            raise RuntimeError("модуль уже выключен")
        # direct: сообщение отправляет сам бот, поэтому на кнопках работают премиум-иконки.
        unit = self.units.add(
            owner,
            "form",
            {"text": text, "rich": rich, "banner": None, "direct": True},
            [self.app.client.me.id],
            ttl=ttl,
        )
        try:
            markup = self._keyboard(unit, buttons)
            unit.data["markup"] = markup
            sent = await self.app.bot.send_message(
                chat_id,
                self._text(text),
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
                disable_notification=True,
                message_thread_id=thread,
                **self._rich(rich),
            )
            unit.data["chat_id"] = chat_id
            unit.data["message_id"] = sent.id
        except BaseException:
            self.units.remove(unit.id)
            raise
        return unit

    async def _query(self, bot, query):
        unit = self.units.get((query.query or "").removeprefix("elys:"))
        results = []
        # Выдача форм только владельцу. allowed_ids разрешает нажатия, не получение формы.
        if unit and query.from_user and query.from_user.id == self.app.client.me.id:
            data = unit.data
            if unit.kind == "gallery":
                photo = data["photos"][data["index"]]
                caption = PLACEHOLDER if "sent" in data else self._text(photo.caption)
                result = InlineQueryResultPhoto(
                    photo.url, id=unit.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=data["markup"]
                )
            else:
                result = InlineQueryResultArticle(
                    "Elys",
                    id=unit.id,
                    input_message_content=InputTextMessageContent(
                        PLACEHOLDER if "sent" in data else self._text(data["text"]),
                        parse_mode=ParseMode.HTML,
                        link_preview_options=preview(data["banner"], self.app.banners_enabled),
                    ),
                    reply_markup=data["markup"],
                )
            results.append(result)
        await query.answer(results, cache_time=0, is_personal=True)
        raise StopPropagation

    async def _callback(self, bot, query):
        match = _CALLBACK.fullmatch(query.data)
        unit = self.units.get(match[1])
        if not unit:
            await query.answer(self._t("gone"), show_alert=True)
        elif not query.from_user or query.from_user.id not in unit.allowed_ids:
            await query.answer(self._t("owner"), show_alert=True)
        else:
            if getattr(query, "inline_message_id", None):
                unit.data["inline_message_id"] = query.inline_message_id
            if query.from_user.id == self.app.client.me.id and isinstance(query.from_user.is_premium, bool):
                self.app.premium = query.from_user.is_premium  # нажатие владельца тоже несёт Premium
            # Не удерживаем воркер диспетчера: callback может выгрузить модуль.
            unit.owner_module.spawn(self._run(unit, query, int(match[2])))
        raise StopPropagation

    async def _run(self, unit, query, index):
        async with unit.lock:
            if self.units.get(unit.id) is not unit or index not in unit.buttons:
                await query.answer(self._t("changed"))
                return
            button = unit.buttons[index]
            try:
                await button.callback(self.app.bot, query, button.data)
                with suppress(QueryIdInvalid):
                    await query.answer()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Не сработала кнопка модуля %s", unit.owner_module.name)
                with suppress(QueryIdInvalid):
                    await query.answer(self._t("failed"), show_alert=True)

    def from_query(self, query):
        match = _CALLBACK.fullmatch(query.data or "")
        return self.units.get(match[1]) if match else None

    async def edit_unit(self, unit, text, buttons=(), *, banner=None, rich=None):
        if not unit:
            return
        old_buttons = unit.buttons
        markup = self._keyboard(unit, buttons)
        try:
            if unit.data.get("inline_message_id"):
                await self.app.bot.edit_inline_text(
                    unit.data["inline_message_id"],
                    self._text(text),
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                    **self._rich(rich),
                    link_preview_options=preview(banner, self.app.banners_enabled),
                )
            elif unit.data.get("chat_id") and unit.data.get("message_id"):
                await self.app.bot.edit_message_text(
                    unit.data["chat_id"],
                    unit.data["message_id"],
                    self._text(text),
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                    **self._rich(rich),
                    link_preview_options=preview(banner, self.app.banners_enabled),
                )
        except MessageNotModified:
            pass
        except BaseException:
            unit.buttons = old_buttons
            raise
        unit.data.update(text=text, rich=rich, markup=markup, banner=banner)

    async def edit(self, target, text, buttons=(), *, banner=None, rich=None):
        if hasattr(target, "owner_module"):
            return await self.edit_unit(target, text, buttons, banner=banner, rich=rich)
        unit = self.from_query(target)
        if not unit:
            return
        if getattr(target, "inline_message_id", None):
            unit.data["inline_message_id"] = target.inline_message_id
        old_buttons = unit.buttons
        markup = self._keyboard(unit, buttons)
        try:
            await target.edit_message_text(
                self._text(text),
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                link_preview_options=preview(banner, self.app.banners_enabled),
                **self._rich(rich),
            )
        except MessageNotModified:
            pass
        except BaseException:
            unit.buttons = old_buttons
            raise
        unit.data.update(text=text, rich=rich, markup=markup, banner=banner)

    async def _dismiss(self, bot, query, data):
        unit = self.from_query(query)
        if unit:
            chat_id = unit.data.get("chat_id")
            message_id = unit.data.get("message_id")
            deleted = False
            if chat_id is not None and message_id is not None:
                with suppress(Exception):
                    if unit.data.get("direct"):
                        await self.app.bot.delete_messages(chat_id, message_id)
                    else:
                        await self.app.client.delete_messages(chat_id, message_id, revoke=True)
                    deleted = True
            if not deleted:
                if unit.kind == "gallery":
                    await query.edit_message_caption(self._t("gallery_closed"), reply_markup=None)
                else:
                    await self.edit(query, self._t("closed"))
            self.units.remove(unit.id)

    async def listing(self, owner, message, pages, **kwargs):
        pages = tuple(pages)
        if not pages:
            raise ValueError("списку нужна хотя бы одна страница")

        async def navigate(bot, query, index):
            await self.edit(
                query,
                pages[index],
                [*page_buttons(index, len(pages), navigate), [close_button(self._dismiss)]],
                banner=kwargs.get("banner"),
            )

        return await self.form(
            owner,
            message,
            pages[0],
            [*page_buttons(0, len(pages), navigate), [close_button(self._dismiss)]],
            kind="list",
            **kwargs,
        )

    async def gallery(self, owner, message, photos, **kwargs):
        photos = tuple(photos)
        if not photos:
            raise ValueError("галерее нужна хотя бы одна фотография")

        async def navigate(bot, query, index):
            unit = self.from_query(query)
            if unit is None:
                return
            old_buttons = unit.buttons
            markup = self._keyboard(unit, [*page_buttons(index, len(photos), navigate), [close_button(self._dismiss)]])
            photo = photos[index]
            try:
                await query.edit_message_media(
                    InputMediaPhoto(photo.url, caption=self._text(photo.caption), parse_mode=ParseMode.HTML),
                    reply_markup=markup,
                )
            except BaseException:
                unit.buttons = old_buttons
                raise
            unit.data.update(index=index, markup=markup)

        return await self.form(
            owner,
            message,
            photos[0].caption,
            [*page_buttons(0, len(photos), navigate), [close_button(self._dismiss)]],
            kind="gallery",
            data={"photos": photos, "index": 0},
            **kwargs,
        )
