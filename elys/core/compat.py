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


class _LegacyPageBlockBlockquote(TLObject):
    __slots__ = ["caption", "collapsed", "text"]
    ID = 0x263d7c26
    QUALNAME = "types.PageBlockBlockquote"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PageBlockBlockquote:
        text = TLObject.read(b)
        caption = TLObject.read(b)
        return raw.types.PageBlockBlockquote(text=text, caption=caption)


class _LegacyPageBlockOrderedList(TLObject):
    __slots__ = ["items", "reversed", "start", "type"]
    ID = 0x9a8ae1e1
    QUALNAME = "types.PageBlockOrderedList"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PageBlockOrderedList:
        items = TLObject.read(b)
        return raw.types.PageBlockOrderedList(items=items)


class _LegacyPageListItemText(TLObject):
    __slots__ = ["checkbox", "checked", "text"]
    ID = 0xb92fb6cd
    QUALNAME = "types.PageListItemText"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PageListItemText:
        text = TLObject.read(b)
        return raw.types.PageListItemText(text=text)


class _LegacyPageListItemBlocks(TLObject):
    __slots__ = ["blocks", "checkbox", "checked"]
    ID = 0x25e073fc
    QUALNAME = "types.PageListItemBlocks"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PageListItemBlocks:
        blocks = TLObject.read(b)
        return raw.types.PageListItemBlocks(blocks=blocks)


class _LegacyPageListOrderedItemText(TLObject):
    __slots__ = ["checkbox", "checked", "num", "text", "type", "value"]
    ID = 0x5e068047
    QUALNAME = "types.PageListOrderedItemText"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PageListOrderedItemText:
        num = String.read(b)
        text = TLObject.read(b)
        return raw.types.PageListOrderedItemText(num=num, text=text)


class _LegacyPageListOrderedItemBlocks(TLObject):
    __slots__ = ["blocks", "checkbox", "checked", "num", "type", "value"]
    ID = 0x98dd8936
    QUALNAME = "types.PageListOrderedItemBlocks"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PageListOrderedItemBlocks:
        num = String.read(b)
        blocks = TLObject.read(b)
        return raw.types.PageListOrderedItemBlocks(num=num, blocks=blocks)


class _LegacyMessageEntityBlockquote(TLObject):
    __slots__ = ["collapsed", "length", "offset"]
    ID = 0x020df5d0
    QUALNAME = "types.MessageEntityBlockquote"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageEntityBlockquote:
        offset = Int.read(b)
        length = Int.read(b)
        return raw.types.MessageEntityBlockquote(offset=offset, length=length)


class _LegacyMessageMediaWebPage(TLObject):
    __slots__ = ["force_large_media", "force_small_media", "manual", "safe", "webpage"]
    ID = 0xa32dd600
    QUALNAME = "types.MessageMediaWebPage"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageMediaWebPage:
        webpage = TLObject.read(b)
        return raw.types.MessageMediaWebPage(webpage=webpage)


class _LegacyTextEmpty(TLObject):
    __slots__: list[str] = []
    ID = 0x0dc10c20
    QUALNAME = "types.TextEmpty"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.TextEmpty:
        return raw.types.TextEmpty()


class _LegacyUserStatusRecently(TLObject):
    __slots__ = ["by_me"]
    ID = 0xe26f42f1
    QUALNAME = "types.UserStatusRecently"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UserStatusRecently:
        return raw.types.UserStatusRecently()


class _LegacyUserStatusLastWeek(TLObject):
    __slots__ = ["by_me"]
    ID = 0x07bf09fc
    QUALNAME = "types.UserStatusLastWeek"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UserStatusLastWeek:
        return raw.types.UserStatusLastWeek()


class _LegacyUserStatusLastMonth(TLObject):
    __slots__ = ["by_me"]
    ID = 0x77ebc742
    QUALNAME = "types.UserStatusLastMonth"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UserStatusLastMonth:
        return raw.types.UserStatusLastMonth()


class _LegacyChatParticipant(TLObject):
    __slots__ = ["date", "inviter_id", "rank", "user_id"]
    ID = 0xc02d4007
    QUALNAME = "types.ChatParticipant"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.ChatParticipant:
        user_id = Long.read(b)
        inviter_id = Long.read(b)
        date = Int.read(b)
        return raw.types.ChatParticipant(user_id=user_id, inviter_id=inviter_id, date=date)


class _LegacyChatParticipantCreator(TLObject):
    __slots__ = ["rank", "user_id"]
    ID = 0xe46bcee4
    QUALNAME = "types.ChatParticipantCreator"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.ChatParticipantCreator:
        user_id = Long.read(b)
        return raw.types.ChatParticipantCreator(user_id=user_id)


class _LegacyChatParticipantAdmin(TLObject):
    __slots__ = ["date", "inviter_id", "rank", "user_id"]
    ID = 0xa0933f5b
    QUALNAME = "types.ChatParticipantAdmin"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.ChatParticipantAdmin:
        user_id = Long.read(b)
        inviter_id = Long.read(b)
        date = Int.read(b)
        return raw.types.ChatParticipantAdmin(user_id=user_id, inviter_id=inviter_id, date=date)


class _LegacyChannelParticipant(TLObject):
    __slots__ = ["date", "rank", "subscription_until_date", "user_id"]
    ID = 0xc00c07c0
    QUALNAME = "types.ChannelParticipant"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.ChannelParticipant:
        user_id = Long.read(b)
        date = Int.read(b)
        return raw.types.ChannelParticipant(user_id=user_id, date=date)


class _LegacyChannelParticipantSelf(TLObject):
    __slots__ = ["date", "inviter_id", "rank", "subscription_until_date", "user_id", "via_request"]
    ID = 0x35a8bfa7
    QUALNAME = "types.ChannelParticipantSelf"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.ChannelParticipantSelf:
        flags = Int.read(b)
        via_request = bool(flags & (1 << 0))
        user_id = Long.read(b)
        inviter_id = Long.read(b)
        date = Int.read(b)
        return raw.types.ChannelParticipantSelf(
            user_id=user_id, inviter_id=inviter_id, date=date, via_request=via_request
        )


class _LegacyChannelParticipantBanned(TLObject):
    __slots__ = ["banned_rights", "date", "kicked_by", "left", "peer", "rank"]
    ID = 0x6df8014e
    QUALNAME = "types.ChannelParticipantBanned"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.ChannelParticipantBanned:
        flags = Int.read(b)
        left = bool(flags & (1 << 0))
        peer = TLObject.read(b)
        kicked_by = Long.read(b)
        date = Int.read(b)
        banned_rights = TLObject.read(b)
        return raw.types.ChannelParticipantBanned(
            left=left, peer=peer, kicked_by=kicked_by, date=date, banned_rights=banned_rights
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
    _LegacyPageBlockBlockquote,
    _LegacyPageBlockOrderedList,
    _LegacyPageListItemText,
    _LegacyPageListItemBlocks,
    _LegacyPageListOrderedItemText,
    _LegacyPageListOrderedItemBlocks,
    _LegacyMessageEntityBlockquote,
    _LegacyMessageMediaWebPage,
    _LegacyTextEmpty,
    _LegacyUserStatusRecently,
    _LegacyUserStatusLastWeek,
    _LegacyUserStatusLastMonth,
    _LegacyChatParticipant,
    _LegacyChatParticipantCreator,
    _LegacyChatParticipantAdmin,
    _LegacyChannelParticipant,
    _LegacyChannelParticipantSelf,
    _LegacyChannelParticipantBanned,
)


def register_legacy_types() -> None:
    for cls in _LEGACY_TYPES:
        raw.all.objects[cls.ID] = cls
        raw.core.tl_object.objects[cls.ID] = cls

