# хелперы для команд.

from __future__ import annotations

from typing import Any

from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError
from pyrogram.types import Message

from elys.ui.banner import preview
from elys.ui.emoji import render

from .context import current


class UserError(Exception):
    # ошибка пользователя: обычный текст (не html), без трейсбека и записи в лог.
    pass


async def respond(message: Message, text: str = "", *, rich_text: str | None = None,
                  banner: str | None = None, **kwargs: Any) -> Message:
    # своё сообщение — редактируем, чужое (sudo) — отвечаем.
    app = current.get()
    is_premium = bool(getattr(app, "premium", False))
    sender = getattr(message, "from_user", None)
    me_id = getattr(getattr(getattr(message, "_client", None), "me", None), "id", None)
    is_own = (
        bool(message.outgoing)
        or (sender is not None and getattr(sender, "is_self", False))
        or (sender is not None and me_id is not None and sender.id == me_id)
        or (me_id is not None and getattr(getattr(message, "chat", None), "id", None) == me_id)
    )

    if rich_text and is_premium:
        rendered_rich = render(rich_text, premium=True)
        try:
            if is_own:
                return await message.edit_text(rich_text=rendered_rich, rich_text_parse_mode=ParseMode.HTML)
            if hasattr(message, "reply_rich"):
                return await message.reply_rich(rendered_rich, parse_mode=ParseMode.HTML)
        except RPCError:
            pass
        except TypeError:
            pass

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
