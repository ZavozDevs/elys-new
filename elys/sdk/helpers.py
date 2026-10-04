"""хелперы для команд."""

from __future__ import annotations

from typing import Any

from pyrogram.types import LinkPreviewOptions, Message

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


class UserError(Exception):
    """ошибка пользователя: обычный текст (не HTML), без трейсбека и записи в лог."""


async def respond(message: Message, text: str, **kwargs: Any) -> Message:
    """своё сообщение — редактируем, чужое (sudo) — отвечаем."""
    kwargs.setdefault("link_preview_options", _NO_PREVIEW)
    if message.outgoing:
        return await message.edit_text(text, **kwargs)
    return await message.reply(text, **kwargs)


async def get_reply(message: Message) -> Message | None:
    """сообщение, на которое ответили (fetch_replies выключен — грузим явно)."""
    if message.reply_to_message is not None:
        return message.reply_to_message
    if not message.reply_to_message_id:
        return None
    reply = await message._client.get_messages(message.chat.id, reply_to_message_ids=message.id)
    return None if reply is None or reply.empty else reply


def raw_args(message: Message) -> str:
    """аргументы команды одной строкой, как есть."""
    parts = (message.text or message.caption or "").split(None, 1)
    return parts[1] if len(parts) > 1 else ""
