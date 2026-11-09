# совместимость tl: legacy-конструкторы replyInlineMarkup и кнопок keyboardButton*.

from __future__ import annotations

from io import BytesIO
from typing import Any

from pyrogram import raw
from pyrogram.raw.core import TLObject
from pyrogram.raw.core.primitives import Bytes, Int, Long, String, Vector


class _LegacyReplyInlineMarkup(TLObject):
    __slots__ = ["rows"]
    ID = 0x48a30254
    QUALNAME = "types.ReplyInlineMarkup"

    def __init__(self, *, rows: list[raw.base.KeyboardInlineButtonRow]) -> None:
        self.rows = rows

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.ReplyInlineMarkup:
        rows = TLObject.read(b)
        return raw.types.ReplyInlineMarkup(rows=rows)

    def write(self, *args: Any) -> bytes:
        b = BytesIO()
        b.write(Int(self.ID, False))
        b.write(Vector(self.rows))
        return b.getvalue()


class _LegacyKeyboardButtonUrl(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xd80c25ec
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        url = String.read(b)
        return raw.types.KeyboardInlineButton(text=text, type=raw.types.InlineButtonTypeUrl(url=url), style=style)


class _LegacyKeyboardButtonCallback(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xe62bc960
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        requires_password = bool(flags & (1 << 0))
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        data = Bytes.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeCallback(data=data, requires_password=requires_password),
            style=style,
        )


class _LegacyKeyboardButtonSwitchInline(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x991399fc
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        same_peer = bool(flags & (1 << 0))
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        query = String.read(b)
        peer_types = TLObject.read(b) if flags & (1 << 1) else None
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeSwitchInline(query=query, same_peer=same_peer, peer_types=peer_types),
            style=style,
        )


class _LegacyKeyboardButtonCopy(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xbcc4af10
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        copy_text = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeCopy(copy_text=copy_text),
            style=style,
        )


class _LegacyKeyboardButtonWebView(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xe846b1a0
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        url = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeWebView(url=url),
            style=style,
        )


class _LegacyKeyboardButtonSimpleWebView(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xe15c4370
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        url = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeWebView(url=url),
            style=style,
        )


class _LegacyKeyboardButtonUrlAuth(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xf51006f9
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        style = TLObject.read(b) if flags & (1 << 10) else None
        fwd_text = String.read(b) if flags & (1 << 0) else None
        text = String.read(b)
        url = String.read(b)
        button_id = Int.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeUrlAuth(url=url, button_id=button_id, fwd_text=fwd_text),
            style=style,
        )


class _LegacyKeyboardButtonUserProfile(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xc0fd5d09
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        user_id = Long.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeUserProfile(user_id=user_id),
            style=style,
        )


class _LegacyKeyboardButtonBuy(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x3fa53905
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeBuy(),
            style=style,
        )


class _LegacyKeyboardButtonGame(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x89c590f9
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        style = TLObject.read(b) if flags & (1 << 10) else None
        text = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeGame(),
            style=style,
        )


class _LegacyPageBlockBlockquote(TLObject):
    __slots__ = ["caption", "collapsed", "text"]
    ID = 0x263d7c26
    QUALNAME = "types.PageBlockBlockquote"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PageBlockBlockquote:
        text = TLObject.read(b)
        caption = TLObject.read(b)
        return raw.types.PageBlockBlockquote(text=text, caption=caption)


_LEGACY_TYPES = (
    _LegacyReplyInlineMarkup,
    _LegacyKeyboardButtonUrl,
    _LegacyKeyboardButtonCallback,
    _LegacyKeyboardButtonSwitchInline,
    _LegacyKeyboardButtonCopy,
    _LegacyKeyboardButtonWebView,
    _LegacyKeyboardButtonSimpleWebView,
    _LegacyKeyboardButtonUrlAuth,
    _LegacyKeyboardButtonUserProfile,
    _LegacyKeyboardButtonBuy,
    _LegacyKeyboardButtonGame,
    _LegacyPageBlockBlockquote,
)


def register_legacy_types() -> None:
    for cls in _LEGACY_TYPES:
        raw.all.objects[cls.ID] = cls
        raw.core.tl_object.objects[cls.ID] = cls

