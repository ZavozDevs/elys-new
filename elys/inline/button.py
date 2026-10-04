from dataclasses import dataclass
from typing import Any

from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton

from elys.ui.emoji import REGISTRY


@dataclass(frozen=True)
class Button:
    text: str
    callback: Any = None
    data: Any = None
    url: str | None = None
    icon: str | None = None
    style: str = "default"
    query: str | None = None

    def render(self, callback_data=None, *, premium=False, direct=False):
        # Премиум-иконку Telegram принимает только в сообщении, которое бот отправил сам (direct), и
        # только при Premium у владельца; в inline-сообщении он вырезает её даже при правке ботом
        # (проверено на живом аккаунте). Там иконку заменяет обычный эмодзи перед текстом.
        targets = bool(self.callback) + bool(self.url) + (self.query is not None)
        if targets != 1:
            raise ValueError("кнопке нужна либо функция callback, либо ссылка url, либо query")
        style = ButtonStyle[self.style.upper()]
        text, icon = self.text, None
        if self.icon:
            identity, fallback = REGISTRY[self.icon]
            if direct and premium:
                icon = identity
            else:
                text = f"{fallback} {text}"
        query = None
        if self.query is not None:
            unit_id = callback_data.split(":")[0] if callback_data else ""
            query = self.query.replace("{unit_id}", unit_id)
        return InlineKeyboardButton(text, callback_data=callback_data if self.callback else None,
                                    url=self.url, switch_inline_query_current_chat=query,
                                    style=style, icon_custom_emoji_id=icon)
