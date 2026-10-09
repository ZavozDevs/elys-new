# хелперы для команд.

from __future__ import annotations

from typing import Any

from pyrogram.types import Message

from elys.ui.banner import preview

from .context import current


class UserError(Exception):
    # ошибка пользователя: обычный текст (не html), без трейсбека и записи в лог.
    pass


async def respond(message: Message, text: str, *, banner: str | None = None, **kwargs: Any) -> Message:
    # своё сообщение — редактируем, чужое (sudo) — отвечаем.
    kwargs.setdefault("link_preview_options", preview(banner, getattr(current.get(), "banners_enabled", True)))
    sender = getattr(message, "from_user", None)
    client_me = getattr(getattr(message, "_client", None), "me", None)
    me_id = getattr(client_me, "id", None)
    is_self = (
        bool(message.outgoing)
        or (sender is not None and getattr(sender, "is_self", False))
        or (sender is not None and me_id is not None and sender.id == me_id)
        or (me_id is not None and getattr(getattr(message, "chat", None), "id", None) == me_id)
    )
    if is_self:
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
