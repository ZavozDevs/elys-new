from __future__ import annotations

import asyncio
import logging
import re
from contextlib import suppress

from pyrogram import StopPropagation, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified, QueryIdInvalid, RPCError
from pyrogram.handlers import (
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    InlineQueryHandler,
    MessageHandler,
)
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputMediaPhoto,
    InputTextMessageContent,
)

from elys.core.registry import change_handler
from elys.ui.banner import preview
from elys.ui.emoji import PLACEHOLDER, render

from .button import Button
from .list import page_buttons
from .units import Units

log = logging.getLogger(__name__)
GROUP = -1000
_CALLBACK = re.compile(r"^([A-Za-z0-9]{8}):(\d+)$")


class Inline:
    def __init__(self, app):
        self.app = app
        self.units = Units()
        self._cleaner = None
        self._handlers = []

    async def start(self):
        async def unit_query(_, client, query):
            q = query.query
            return q.startswith("elys:") or q.startswith("cfg ") or q.startswith("cfg:")

        async def unit_callback(_, client, query):
            return isinstance(query.data, str) and bool(_CALLBACK.fullmatch(query.data))

        async def unit_chosen(_, client, result):
            rid = getattr(result, "result_id", None)
            q = getattr(result, "query", "") or ""
            return self.units.get(rid) is not None or q.startswith("cfg ") or q.startswith("cfg:")

        handlers = [InlineQueryHandler(self._query, filters.create(unit_query)),
                    CallbackQueryHandler(self._callback, filters.create(unit_callback)),
                    ChosenInlineResultHandler(self._chosen, filters.create(unit_chosen))]
        for handler in handlers:
            await change_handler(self.app.bot, handler, GROUP)
            self._handlers.append(handler)

        async def is_ephemeral(_, client, message):
            via = getattr(message, "via_bot", None)
            bot_me = getattr(getattr(self.app, "bot", None), "me", None)
            return bool(
                getattr(message, "outgoing", False)
                and via
                and bot_me
                and getattr(via, "id", None) == getattr(bot_me, "id", None)
                and (message.text or message.caption)
                and "Применяю" in (message.text or message.caption)
            )

        async def delete_ephemeral(client, message):
            with suppress(Exception):
                await message.delete()

        self._ephemeral_handler = MessageHandler(delete_ephemeral, filters.create(is_ephemeral))
        await change_handler(self.app.client, self._ephemeral_handler, -998)
        self._cleaner = asyncio.create_task(self.units.clean())

    async def close(self):
        if hasattr(self, "_ephemeral_handler"):
            await change_handler(self.app.client, self._ephemeral_handler, -998, remove=True)
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
                rendered.append(button.render(f"{unit.id}:{index}", premium=self.app.premium,
                                                direct=unit.data.get("direct", False)))
                if button.callback:
                    buttons[index] = button
            if rendered:
                keyboard.append(rendered)
        unit.buttons = buttons
        return InlineKeyboardMarkup(keyboard) if keyboard else None

    def _text(self, text):
        return render(text, self.app.premium)

    def _deferred(self, text):
        # Премиум-эмодзи нельзя отправить в inline-результате: отправляем заглушку, затем правим.
        # Нужен Inline Feedback (флаг bot_feedback ставит BotService), иначе inline_message_id не узнать.
        core = self.app.kv.ns("core")
        return bool(self.app.premium and core.get("bot_feedback") and core.get("bot_feedback") == core.get("bot_token")
                    and "<tg-emoji" in self._text(text))

    async def form(self, owner, message, text, buttons=(), *, banner=None, allowed_ids=None, ttl=86400,
                   kind="form", data=None):
        if not owner.loaded:
            raise RuntimeError("модуль уже выключен")
        unit = self.units.add(owner, kind, {"text": text, "banner": banner, **(data or {})},
                              [self.app.client.me.id] if allowed_ids is None else allowed_ids, ttl=ttl)
        try:
            if self._deferred(text):
                unit.data["sent"] = asyncio.get_running_loop().create_future()
            rows = list(buttons) or [[Button("Закрыть", self._dismiss)]]
            unit.data["markup"] = self._keyboard(unit, rows)
            results = await self.app.client.get_inline_bot_results(self.app.bot.me.username, f"elys:{unit.id}")
            if not results.results:
                raise RuntimeError("Бот не вернул форму. Перезапусти Elys и попробуй снова.")
            chat_id = message if isinstance(message, int) else message.chat.id
            await self.app.client.send_inline_bot_result(
                chat_id, results.query_id, unit.id,
                message_thread_id=getattr(message, "message_thread_id", None),
            )
            if "sent" in unit.data:
                await self._finish(unit)
            return unit
        except BaseException:
            self.units.remove(unit.id)
            raise

    async def _chosen(self, bot, result):
        q = getattr(result, "query", "") or ""
        if q.startswith("cfg ") or q.startswith("cfg:"):
            from_user = getattr(result, "from_user", None)
            if from_user and from_user.id == self.app.client.me.id:
                await self._chosen_cfg(result)
            raise StopPropagation
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
            log.warning("Telegram не сообщил о выбранной форме, премиум-эмодзи не показаны. "
                        "Проверь Inline Feedback бота в @BotFather.")
            return
        finally:
            unit.data.pop("sent", None)  # дальше форма обычная: повторный запрос получит полный текст
        for attempt in range(4):
            try:
                if unit.kind == "gallery":
                    await self.app.bot.edit_inline_caption(
                        inline_id, self._text(unit.data["text"]), parse_mode=ParseMode.HTML,
                        reply_markup=unit.data["markup"])
                else:
                    await self.app.bot.edit_inline_text(
                        inline_id, self._text(unit.data["text"]), parse_mode=ParseMode.HTML,
                        reply_markup=unit.data["markup"],
                        link_preview_options=preview(unit.data["banner"], self.app.banners_enabled))
                return
            except MessageNotModified:
                return
            except RPCError:
                if attempt == 3:
                    log.exception("Не удалось показать премиум-эмодзи в форме")
                    return
                await asyncio.sleep(0.1 * 2 ** attempt)

    async def bot_form(self, owner, chat_id, text, buttons=(), *, ttl=86400):
        if not owner.loaded:
            raise RuntimeError("модуль уже выключен")
        # direct: сообщение отправляет сам бот, поэтому на кнопках работают премиум-иконки.
        unit = self.units.add(owner, "form", {"text": text, "banner": None, "direct": True},
                              [self.app.client.me.id], ttl=ttl)
        try:
            markup = self._keyboard(unit, buttons)
            unit.data["markup"] = markup
            sent = await self.app.bot.send_message(chat_id, self._text(text), reply_markup=markup,
                                                   parse_mode=ParseMode.HTML, disable_notification=True)
            unit.data["chat_id"] = chat_id
            unit.data["message_id"] = sent.id
        except BaseException:
            self.units.remove(unit.id)
            raise
        return unit

    def _parse_cfg_query(self, text: str):
        if text.startswith("cfg ") or text.startswith("cfg:"):
            raw = text[4:].strip()
        else:
            return None

        parts = raw.split(" ", 1)
        target_spec = parts[0].strip()
        val = parts[1].strip() if len(parts) > 1 else ""

        from elys.builtin.configure import _input_tokens
        if target_spec in _input_tokens:
            action, mod_name, key = _input_tokens[target_spec]
            return None, action, mod_name, key, val

        if ":" in target_spec:
            tokens = target_spec.split(":")
            if len(tokens) >= 3 and tokens[1] == "core":
                return tokens[0], "core", "core", tokens[2], val
            if len(tokens) >= 4 and tokens[1] in {"set", "add"}:
                return tokens[0], tokens[1], tokens[2], tokens[3], val

        action = "add" if target_spec.startswith("+") else "set"
        clean = target_spec.lstrip("+")
        unit_id = None

        if "." in clean:
            mod_name, key = clean.split(".", 1)
        elif ":" in clean:
            mod_name, key = clean.split(":", 1)
        elif clean in {"prefixes", "language", "banners", "aliases", "start_banner"}:
            mod_name, key = "core", clean
        else:
            mod_name, key = "", clean
            for m in self.app.modules.values():
                if m.config and clean in m.config.fields:
                    mod_name = m.name
                    break

        return unit_id, action, mod_name, key, val

    async def _query_cfg(self, query):
        if not query.from_user or query.from_user.id != self.app.client.me.id:
            await query.answer([], cache_time=0, is_personal=True)
            return

        parsed = self._parse_cfg_query(query.query or "")
        if not parsed:
            await query.answer([], cache_time=0, is_personal=True)
            return

        _unit_id, action, mod_name, key, val = parsed
        label = f"{mod_name} · {key}" if mod_name and mod_name != "core" else key

        if val:
            act_text = "Добавить" if action == "add" else "Сохранить"
            title = f"{act_text}: {val}"
            desc = f"{label} · Нажми для сохранения"
            msg_text = f"🔄 <i>Применяю {label}...</i>"
        else:
            title = f"Введи значение для {label}..."
            desc = "Напиши значение после пробела"
            msg_text = "ℹ️ Новое значение не указано"

        result = InlineQueryResultArticle(
            title=title,
            description=desc,
            id=f"cfg:{key}",
            input_message_content=InputTextMessageContent(msg_text, parse_mode=ParseMode.HTML),
        )
        await query.answer([result], cache_time=0, is_personal=True)

    async def _chosen_cfg(self, result):
        parsed = self._parse_cfg_query(getattr(result, "query", "") or "")
        if not parsed:
            return

        unit_id, action, mod_name, key, val = parsed
        if not val:
            if getattr(result, "inline_message_id", None):
                with suppress(Exception):
                    await self.app.bot.edit_inline_text(result.inline_message_id, "❌ Значение не было указано.")
            return

        try:
            from elys.builtin.configure import apply_core, parse_item, parse_value, screen, target
            route = None
            if mod_name == "core":
                apply_core(self.app, key, val)
                route = ("core_field", key)
            elif mod_name:
                item = target(mod_name)
                field = item.config.fields[key]
                if action == "add":
                    curr = list(item.config[key])
                    curr.append(parse_item(field, val))
                    item.config[key] = curr
                else:
                    item.config[key] = parse_value(field, val)
                route = ("field", mod_name, key, 0)
            else:
                return

            unit = self.units.get(unit_id) if unit_id else next(
                (u for u in reversed(self.units.items.values()) if u.owner_module.name == "Configure"), None
            )
            if unit and route:
                text, rows = screen(route)
                await self.edit_unit(unit, text, rows)
        except (ValueError, TypeError) as exc:
            log.warning("Некорректное значение для настройки %s.%s: %s", mod_name, key, exc)
            unit = self.units.get(unit_id) if unit_id else next(
                (u for u in reversed(self.units.items.values()) if u.owner_module.name == "Configure"), None
            )
            if unit and route:
                with suppress(Exception):
                    cur_text, cur_rows = screen(route)
                    await self.edit_unit(unit, f"⚠️ <b>Значение не подходит:</b> {exc}\n\n" + cur_text, cur_rows)
        except Exception:
            log.exception("Не удалось применить настройку через inline query")

    async def _query(self, bot, query):
        q = query.query or ""
        if q.startswith("cfg ") or q.startswith("cfg:"):
            await self._query_cfg(query)
            raise StopPropagation
        unit = self.units.get(q.removeprefix("elys:"))
        results = []
        # Выдача форм только владельцу. allowed_ids разрешает нажатия, не получение формы.
        if unit and query.from_user and query.from_user.id == self.app.client.me.id:
            data = unit.data
            if unit.kind == "gallery":
                photo = data["photos"][data["index"]]
                caption = PLACEHOLDER if "sent" in data else self._text(photo.caption)
                result = InlineQueryResultPhoto(photo.url, id=unit.id, caption=caption,
                                                parse_mode=ParseMode.HTML, reply_markup=data["markup"])
            else:
                result = InlineQueryResultArticle("Elys", id=unit.id, input_message_content=InputTextMessageContent(
                    PLACEHOLDER if "sent" in data else self._text(data["text"]), parse_mode=ParseMode.HTML,
                    link_preview_options=preview(data["banner"], self.app.banners_enabled),
                ), reply_markup=data["markup"])
            results.append(result)
        await query.answer(results, cache_time=0, is_personal=True)
        raise StopPropagation

    async def _callback(self, bot, query):
        match = _CALLBACK.fullmatch(query.data)
        unit = self.units.get(match[1])
        if not unit:
            await query.answer("Эта форма закрыта или устарела. Открой её командой ещё раз.", show_alert=True)
        elif not query.from_user or query.from_user.id not in unit.allowed_ids:
            await query.answer("Эта кнопка доступна только владельцу формы.", show_alert=True)
        else:
            if getattr(query, "inline_message_id", None):
                unit.data["inline_message_id"] = query.inline_message_id
            # Не удерживаем воркер диспетчера: callback может выгрузить модуль.
            unit.owner_module.spawn(self._run(unit, query, int(match[2])))
        raise StopPropagation

    async def _run(self, unit, query, index):
        async with unit.lock:
            if self.units.get(unit.id) is not unit or index not in unit.buttons:
                await query.answer("Экран уже изменился. Нажми кнопку на новом экране.")
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
                    await query.answer("Кнопка не сработала. Подробности — в теме «Ошибки». "
                                       "Попробуй открыть форму снова.",
                                       show_alert=True)

    def from_query(self, query):
        match = _CALLBACK.fullmatch(query.data or "")
        return self.units.get(match[1]) if match else None

    async def edit_unit(self, unit, text, buttons=(), *, banner=None):
        if not unit:
            return
        old_buttons = unit.buttons
        markup = self._keyboard(unit, buttons)
        try:
            if unit.data.get("inline_message_id"):
                await self.app.bot.edit_inline_text(
                    unit.data["inline_message_id"], self._text(text),
                    parse_mode=ParseMode.HTML, reply_markup=markup,
                    link_preview_options=preview(banner, self.app.banners_enabled),
                )
            elif unit.data.get("chat_id") and unit.data.get("message_id"):
                await self.app.bot.edit_message_text(
                    unit.data["chat_id"], unit.data["message_id"], self._text(text),
                    parse_mode=ParseMode.HTML, reply_markup=markup,
                    link_preview_options=preview(banner, self.app.banners_enabled),
                )
        except MessageNotModified:
            pass
        except BaseException:
            unit.buttons = old_buttons
            raise
        unit.data.update(text=text, markup=markup, banner=banner)

    async def edit(self, target, text, buttons=(), *, banner=None):
        if hasattr(target, "owner_module"):
            return await self.edit_unit(target, text, buttons, banner=banner)
        unit = self.from_query(target)
        if not unit:
            return
        if getattr(target, "inline_message_id", None):
            unit.data["inline_message_id"] = target.inline_message_id
        old_buttons = unit.buttons
        markup = self._keyboard(unit, buttons)
        try:
            await target.edit_message_text(self._text(text), parse_mode=ParseMode.HTML, reply_markup=markup,
                                           link_preview_options=preview(banner, self.app.banners_enabled))
        except MessageNotModified:
            pass
        except BaseException:
            unit.buttons = old_buttons
            raise
        unit.data.update(text=text, markup=markup, banner=banner)

    async def _dismiss(self, bot, query, data):
        unit = self.from_query(query)
        if unit:
            if unit.kind == "gallery":
                await query.edit_message_caption("Галерея закрыта.", reply_markup=InlineKeyboardMarkup([]))
            else:
                await self.edit(query, "Меню закрыто. Чтобы открыть его снова, повтори команду.")
            self.units.remove(unit.id)

    async def listing(self, owner, message, pages, **kwargs):
        pages = tuple(pages)
        if not pages:
            raise ValueError("списку нужна хотя бы одна страница")

        async def navigate(bot, query, index):
            await self.edit(query, f"{pages[index]}\n\n<i>{index + 1} / {len(pages)}</i>",
                            [*page_buttons(index, len(pages), navigate), [Button("Закрыть", self._dismiss)]],
                            banner=kwargs.get("banner"))

        return await self.form(owner, message, f"{pages[0]}\n\n<i>1 / {len(pages)}</i>",
                               [*page_buttons(0, len(pages), navigate), [Button("Закрыть", self._dismiss)]],
                               kind="list", **kwargs)

    async def gallery(self, owner, message, photos, **kwargs):
        photos = tuple(photos)
        if not photos:
            raise ValueError("галерее нужна хотя бы одна фотография")

        async def navigate(bot, query, index):
            unit = self.from_query(query)
            if unit is None:
                return
            old_buttons = unit.buttons
            markup = self._keyboard(unit, [*page_buttons(index, len(photos), navigate),
                                           [Button("Закрыть", self._dismiss)]])
            photo = photos[index]
            try:
                await query.edit_message_media(InputMediaPhoto(photo.url, caption=self._text(photo.caption),
                                                               parse_mode=ParseMode.HTML), reply_markup=markup)
            except BaseException:
                unit.buttons = old_buttons
                raise
            unit.data.update(index=index, markup=markup)

        return await self.form(owner, message, photos[0].caption,
                               [*page_buttons(0, len(photos), navigate), [Button("Закрыть", self._dismiss)]],
                               kind="gallery", data={"photos": photos, "index": 0}, **kwargs)
