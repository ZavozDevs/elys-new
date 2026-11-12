# хелперы для команд.

from __future__ import annotations

from contextlib import suppress
from typing import Any

from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError
from pyrogram.types import Message

from elys.ui.banner import preview
from elys.ui.emoji import render
from elys.ui.rich import plain

from .context import current


class UserError(Exception):
    # ошибка пользователя: обычный текст (не html), без трейсбека и записи в лог.
    pass


async def respond(
    message: Message, text: str = "", *, rich_text: str | None = None, banner: str | None = None, **kwargs: Any
) -> Any:
    # своё сообщение — редактируем, чужое (sudo) — отвечаем. rich_text — по режиму app.rich (§12.6);
    # без text обычный вариант строится из rich_text.
    app = current.get()
    is_premium = bool(getattr(app, "premium", False))
    mode = getattr(app, "rich", "auto")
    text = text or render(plain(rich_text or ""), is_premium)
    rich_text = rich_text if mode != "off" else None
    is_own = message.outgoing or getattr(getattr(message, "from_user", None), "is_self", False)  # «Избранное» — тоже

    if rich_text and is_premium:
        rendered = render(rich_text, premium=True)
        with suppress(RPCError):  # Telegram не принял rich (RICH_MESSAGE_UNSUPPORTED и т.п.) — ниже уйдёт обычный текст
            if is_own:
                return await message.edit_text(rich_text=rendered, rich_text_parse_mode=ParseMode.HTML)
            return await message.reply_rich(rendered, parse_mode=ParseMode.HTML)

    # без Premium rich шлёт только бот: форма вместо правки своего сообщения; модуль выгружен — обычный ответ.
    bot = rich_text and mode == "bot" and getattr(message, "command", None) and app.inline.deferred(text, rich_text)
    if bot and (command := app.router.get(message.command[0])):
        unit = await app.inline.form(command.owner, message, text, [[]], banner=banner, rich=rich_text)
        if is_own:
            await message.delete()
        return unit

    kwargs.setdefault("link_preview_options", preview(banner, getattr(app, "banners_enabled", True)))
    if is_own:
        return await message.edit_text(text, **kwargs)
    return await message.reply(text, **kwargs)


async def get_reply(message: Message) -> Message | None:
    # сообщение, на которое ответили (fetch_replies выключен — грузим явно).
    if message.reply_to_message is not None:
        return message.reply_to_message
    if not message.reply_to_message_id:
        return None
    reply = await message._client.get_messages(message.chat.id, reply_to_message_ids=message.id)
    return None if reply is None or reply.empty else reply


def raw_args(message: Message) -> str:
    # аргументы команды одной строкой, как есть.
    parts = (message.text or message.caption or "").split(None, 1)
    return parts[1] if len(parts) > 1 else ""


def format_uptime(seconds: float | int) -> str:
    total_seconds = int(seconds)
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}д {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
