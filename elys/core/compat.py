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


class _LegacyKeyboardButtonUrlOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x258aff05
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        text = String.read(b)
        url = String.read(b)
        return raw.types.KeyboardInlineButton(text=text, type=raw.types.InlineButtonTypeUrl(url=url))


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


class _LegacyKeyboardButtonCallbackOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x35bbdb6b
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        requires_password = bool(flags & (1 << 0))
        text = String.read(b)
        data = Bytes.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeCallback(data=data, requires_password=requires_password),
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


class _LegacyKeyboardButtonSwitchInlineOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x93b9fbb5
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        same_peer = bool(flags & (1 << 0))
        text = String.read(b)
        query = String.read(b)
        peer_types = TLObject.read(b) if flags & (1 << 1) else None
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeSwitchInline(query=query, same_peer=same_peer, peer_types=peer_types),
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


class _LegacyKeyboardButtonWebViewOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x13767230
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        text = String.read(b)
        url = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeWebView(url=url),
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


class _LegacyKeyboardButtonSimpleWebViewOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xa0c0505c
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        text = String.read(b)
        url = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeWebView(url=url),
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


class _LegacyKeyboardButtonUrlAuthOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x10b78d29
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        flags = Int.read(b)
        fwd_text = String.read(b) if flags & (1 << 0) else None
        text = String.read(b)
        url = String.read(b)
        button_id = Int.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeUrlAuth(url=url, button_id=button_id, fwd_text=fwd_text),
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


class _LegacyKeyboardButtonUserProfileOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x308660c1
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        text = String.read(b)
        user_id = Long.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeUserProfile(user_id=user_id),
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


class _LegacyKeyboardButtonBuyOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0xafd93fbb
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        text = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeBuy(),
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


class _LegacyKeyboardButtonGameOld(TLObject):
    __slots__ = ["style", "text", "type"]
    ID = 0x50f41ccf
    QUALNAME = "types.KeyboardInlineButton"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.KeyboardInlineButton:
        text = String.read(b)
        return raw.types.KeyboardInlineButton(
            text=text,
            type=raw.types.InlineButtonTypeGame(),
        )


_LEGACY_TYPES = (
    _LegacyReplyInlineMarkup,
    _LegacyKeyboardButtonUrl,
    _LegacyKeyboardButtonUrlOld,
    _LegacyKeyboardButtonCallback,
    _LegacyKeyboardButtonCallbackOld,
    _LegacyKeyboardButtonSwitchInline,
    _LegacyKeyboardButtonSwitchInlineOld,
    _LegacyKeyboardButtonCopy,
    _LegacyKeyboardButtonWebView,
    _LegacyKeyboardButtonWebViewOld,
    _LegacyKeyboardButtonSimpleWebView,
    _LegacyKeyboardButtonSimpleWebViewOld,
    _LegacyKeyboardButtonUrlAuth,
    _LegacyKeyboardButtonUrlAuthOld,
    _LegacyKeyboardButtonUserProfile,
    _LegacyKeyboardButtonUserProfileOld,
    _LegacyKeyboardButtonBuy,
    _LegacyKeyboardButtonBuyOld,
    _LegacyKeyboardButtonGame,
    _LegacyKeyboardButtonGameOld,
)


def register_legacy_types() -> None:
    for cls in _LEGACY_TYPES:
        raw.all.objects[cls.ID] = cls
        raw.core.tl_object.objects[cls.ID] = cls
