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


class _LegacyWebPageEmpty(TLObject):
    __slots__ = ["id", "url"]
    ID = 0xeb1477e8
    QUALNAME = "types.WebPageEmpty"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.WebPageEmpty:
        page_id = Long.read(b)
        return raw.types.WebPageEmpty(id=page_id)


class _LegacyWebPagePending(TLObject):
    __slots__ = ["date", "id", "url"]
    ID = 0xc586da1c
    QUALNAME = "types.WebPagePending"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.WebPagePending:
        page_id = Long.read(b)
        date = Int.read(b)
        return raw.types.WebPagePending(id=page_id, date=date)


class _LegacyUpdateUserTyping(TLObject):
    __slots__ = ["action", "top_msg_id", "user_id"]
    ID = 0xc01e857f
    QUALNAME = "types.UpdateUserTyping"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateUserTyping:
        user_id = Long.read(b)
        action = TLObject.read(b)
        return raw.types.UpdateUserTyping(user_id=user_id, action=action)


class _LegacyUpdateReadHistoryInbox(TLObject):
    __slots__ = ["folder_id", "max_id", "peer", "pts", "pts_count", "still_unread_count", "top_msg_id"]
    ID = 0x9c974fdf
    QUALNAME = "types.UpdateReadHistoryInbox"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateReadHistoryInbox:
        flags = Int.read(b)
        folder_id = Int.read(b) if flags & (1 << 0) else None
        peer = TLObject.read(b)
        max_id = Int.read(b)
        still_unread_count = Int.read(b)
        pts = Int.read(b)
        pts_count = Int.read(b)
        return raw.types.UpdateReadHistoryInbox(
            peer=peer,
            max_id=max_id,
            still_unread_count=still_unread_count,
            pts=pts,
            pts_count=pts_count,
            folder_id=folder_id,
        )


class _LegacyUpdateReadMessagesContents(TLObject):
    __slots__ = ["date", "messages", "pts", "pts_count"]
    ID = 0x68c13933
    QUALNAME = "types.UpdateReadMessagesContents"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateReadMessagesContents:
        messages = TLObject.read(b)
        pts = Int.read(b)
        pts_count = Int.read(b)
        return raw.types.UpdateReadMessagesContents(messages=messages, pts=pts, pts_count=pts_count)


class _LegacyUpdateDraftMessage(TLObject):
    __slots__ = ["draft", "peer", "saved_peer_id", "top_msg_id"]
    ID = 0x1b49ec6d
    QUALNAME = "types.UpdateDraftMessage"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateDraftMessage:
        flags = Int.read(b)
        peer = TLObject.read(b)
        top_msg_id = Int.read(b) if flags & (1 << 0) else None
        draft = TLObject.read(b)
        return raw.types.UpdateDraftMessage(peer=peer, draft=draft, top_msg_id=top_msg_id)


class _LegacyUpdateChannelReadMessagesContents(TLObject):
    __slots__ = ["channel_id", "messages", "saved_peer_id", "top_msg_id"]
    ID = 0xea29055d
    QUALNAME = "types.UpdateChannelReadMessagesContents"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateChannelReadMessagesContents:
        flags = Int.read(b)
        channel_id = Long.read(b)
        top_msg_id = Int.read(b) if flags & (1 << 0) else None
        messages = TLObject.read(b)
        return raw.types.UpdateChannelReadMessagesContents(
            channel_id=channel_id, messages=messages, top_msg_id=top_msg_id
        )


class _LegacyUpdateDialogUnreadMark(TLObject):
    __slots__ = ["peer", "saved_peer_id", "unread"]
    ID = 0xe16459c3
    QUALNAME = "types.UpdateDialogUnreadMark"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateDialogUnreadMark:
        flags = Int.read(b)
        unread = bool(flags & (1 << 0))
        peer = TLObject.read(b)
        return raw.types.UpdateDialogUnreadMark(peer=peer, unread=unread)


class _LegacyUpdateMessagePoll(TLObject):
    __slots__ = ["msg_id", "peer", "poll", "poll_id", "results", "top_msg_id"]
    ID = 0xaca1657b
    QUALNAME = "types.UpdateMessagePoll"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateMessagePoll:
        flags = Int.read(b)
        poll_id = Long.read(b)
        poll = TLObject.read(b) if flags & (1 << 0) else None
        results = TLObject.read(b)
        return raw.types.UpdateMessagePoll(poll_id=poll_id, results=results, poll=poll)


class _LegacyUpdateMessagePollVote(TLObject):
    __slots__ = ["options", "peer", "poll_id", "positions", "qts"]
    ID = 0x106395c9
    QUALNAME = "types.UpdateMessagePollVote"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateMessagePollVote:
        poll_id = Long.read(b)
        user_id = Long.read(b)
        options = TLObject.read(b)
        qts = Int.read(b)
        peer = raw.types.PeerUser(user_id=user_id)
        return raw.types.UpdateMessagePollVote(poll_id=poll_id, peer=peer, options=options, qts=qts, positions=[])


class _LegacyUpdateDeleteScheduledMessages(TLObject):
    __slots__ = ["messages", "peer", "sent_messages"]
    ID = 0x90866cee
    QUALNAME = "types.UpdateDeleteScheduledMessages"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateDeleteScheduledMessages:
        peer = TLObject.read(b)
        messages = TLObject.read(b)
        return raw.types.UpdateDeleteScheduledMessages(peer=peer, messages=messages)


class _LegacyUpdatePeerBlocked(TLObject):
    __slots__ = ["blocked", "blocked_my_stories_from", "peer_id"]
    ID = 0x246a4b22
    QUALNAME = "types.UpdatePeerBlocked"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdatePeerBlocked:
        peer_id = TLObject.read(b)
        blocked = TLObject.read(b)
        return raw.types.UpdatePeerBlocked(peer_id=peer_id, blocked=blocked)


class _LegacyUpdateMessageReactions(TLObject):
    __slots__ = ["msg_id", "peer", "reactions", "saved_peer_id", "top_msg_id"]
    ID = 0x5e1b3cb8
    QUALNAME = "types.UpdateMessageReactions"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateMessageReactions:
        flags = Int.read(b)
        peer = TLObject.read(b)
        msg_id = Int.read(b)
        top_msg_id = Int.read(b) if flags & (1 << 0) else None
        reactions = TLObject.read(b)
        return raw.types.UpdateMessageReactions(peer=peer, msg_id=msg_id, reactions=reactions, top_msg_id=top_msg_id)


class _LegacyUpdateMessageExtendedMedia(TLObject):
    __slots__ = ["extended_media", "msg_id", "peer"]
    ID = 0x5a73a98c
    QUALNAME = "types.UpdateMessageExtendedMedia"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.UpdateMessageExtendedMedia:
        peer = TLObject.read(b)
        msg_id = Int.read(b)
        media = TLObject.read(b)
        return raw.types.UpdateMessageExtendedMedia(peer=peer, msg_id=msg_id, extended_media=[media])


class _LegacyMessageFwdHeader(TLObject):
    __slots__ = [
        "channel_post",
        "date",
        "from_id",
        "from_name",
        "imported",
        "post_author",
        "psa_type",
        "saved_date",
        "saved_from_id",
        "saved_from_msg_id",
        "saved_from_name",
        "saved_from_peer",
        "saved_out",
    ]
    ID = 0x5f777dce
    QUALNAME = "types.MessageFwdHeader"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageFwdHeader:
        flags = Int.read(b)
        imported = bool(flags & (1 << 7))
        from_id = TLObject.read(b) if flags & (1 << 0) else None
        from_name = String.read(b) if flags & (1 << 5) else None
        date = Int.read(b)
        channel_post = Int.read(b) if flags & (1 << 2) else None
        post_author = String.read(b) if flags & (1 << 3) else None
        saved_from_peer = TLObject.read(b) if flags & (1 << 4) else None
        saved_from_msg_id = Int.read(b) if flags & (1 << 4) else None
        psa_type = String.read(b) if flags & (1 << 6) else None
        return raw.types.MessageFwdHeader(
            date=date,
            imported=imported,
            from_id=from_id,
            from_name=from_name,
            channel_post=channel_post,
            post_author=post_author,
            saved_from_peer=saved_from_peer,
            saved_from_msg_id=saved_from_msg_id,
            psa_type=psa_type,
        )


class _LegacyMessageReplyHeader(TLObject):
    __slots__ = [
        "forum_topic",
        "poll_option",
        "quote",
        "quote_entities",
        "quote_offset",
        "quote_text",
        "reply_from",
        "reply_media",
        "reply_to_ephemeral",
        "reply_to_msg_id",
        "reply_to_peer_id",
        "reply_to_scheduled",
        "reply_to_top_id",
        "todo_item_id",
    ]
    ID = 0xa6d57763
    QUALNAME = "types.MessageReplyHeader"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageReplyHeader:
        flags = Int.read(b)
        reply_to_scheduled = bool(flags & (1 << 2))
        forum_topic = bool(flags & (1 << 3))
        reply_to_msg_id = Int.read(b)
        reply_to_peer_id = TLObject.read(b) if flags & (1 << 0) else None
        reply_to_top_id = Int.read(b) if flags & (1 << 1) else None
        return raw.types.MessageReplyHeader(
            reply_to_scheduled=reply_to_scheduled,
            forum_topic=forum_topic,
            reply_to_msg_id=reply_to_msg_id,
            reply_to_peer_id=reply_to_peer_id,
            reply_to_top_id=reply_to_top_id,
        )


class _LegacyMessageMediaPhoto(TLObject):
    __slots__ = ["live_photo", "photo", "spoiler", "ttl_seconds", "video"]
    ID = 0x695150d7
    QUALNAME = "types.MessageMediaPhoto"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageMediaPhoto:
        flags = Int.read(b)
        spoiler = bool(flags & (1 << 3))
        photo = TLObject.read(b) if flags & (1 << 0) else None
        ttl_seconds = Int.read(b) if flags & (1 << 2) else None
        return raw.types.MessageMediaPhoto(photo=photo, spoiler=spoiler, ttl_seconds=ttl_seconds)


class _LegacyMessageMediaDocument(TLObject):
    __slots__ = [
        "alt_documents",
        "document",
        "nopremium",
        "round",
        "spoiler",
        "ttl_seconds",
        "video",
        "video_cover",
        "video_timestamp",
        "voice",
    ]
    ID = 0x9cb070d7
    QUALNAME = "types.MessageMediaDocument"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageMediaDocument:
        flags = Int.read(b)
        nopremium = bool(flags & (1 << 3))
        spoiler = bool(flags & (1 << 4))
        doc = TLObject.read(b) if flags & (1 << 0) else None
        ttl_seconds = Int.read(b) if flags & (1 << 2) else None
        return raw.types.MessageMediaDocument(
            document=doc, nopremium=nopremium, spoiler=spoiler, ttl_seconds=ttl_seconds
        )


class _LegacyMessageMediaDice(TLObject):
    __slots__ = ["emoticon", "game_outcome", "value"]
    ID = 0x3f7ee58b
    QUALNAME = "types.MessageMediaDice"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageMediaDice:
        value = Int.read(b)
        emoticon = String.read(b)
        return raw.types.MessageMediaDice(value=value, emoticon=emoticon)


class _LegacyMessageMediaPoll(TLObject):
    __slots__ = ["attached_media", "poll", "results"]
    ID = 0x4bd6e798
    QUALNAME = "types.MessageMediaPoll"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageMediaPoll:
        poll = TLObject.read(b)
        results = TLObject.read(b)
        return raw.types.MessageMediaPoll(poll=poll, results=results)


class _LegacyMessageReactions(TLObject):
    __slots__ = ["can_see_list", "min", "reactions_as_tags", "recent_reactions", "results", "top_reactors"]
    ID = 0x4f2b9479
    QUALNAME = "types.MessageReactions"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.MessageReactions:
        flags = Int.read(b)
        min_flag = bool(flags & (1 << 0))
        can_see_list = bool(flags & (1 << 2))
        results = TLObject.read(b)
        recent_reactions = TLObject.read(b) if flags & (1 << 1) else None
        return raw.types.MessageReactions(
            results=results, min=min_flag, can_see_list=can_see_list, recent_reactions=recent_reactions
        )


class _LegacyDraftMessage(TLObject):
    __slots__ = [
        "date",
        "effect",
        "entities",
        "invert_media",
        "media",
        "message",
        "no_webpage",
        "reply_to",
        "rich_message",
        "suggested_post",
    ]
    ID = 0xfd8e711f
    QUALNAME = "types.DraftMessage"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.DraftMessage:
        flags = Int.read(b)
        no_webpage = bool(flags & (1 << 1))
        _reply_to_msg_id = Int.read(b) if flags & (1 << 0) else None
        msg = String.read(b)
        entities = TLObject.read(b) if flags & (1 << 3) else None
        date = Int.read(b)
        return raw.types.DraftMessage(date=date, message=msg, no_webpage=no_webpage, entities=entities)


class _LegacyPoll(TLObject):
    __slots__ = [
        "answers",
        "close_date",
        "close_period",
        "closed",
        "countries_iso2",
        "creator",
        "hash",
        "hide_results_until_close",
        "id",
        "multiple_choice",
        "open_answers",
        "public_voters",
        "question",
        "quiz",
        "revoting_disabled",
        "shuffle_answers",
        "subscribers_only",
    ]
    ID = 0x86e18161
    QUALNAME = "types.Poll"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.Poll:
        poll_id = Long.read(b)
        flags = Int.read(b)
        closed = bool(flags & (1 << 0))
        public_voters = bool(flags & (1 << 1))
        multiple_choice = bool(flags & (1 << 2))
        quiz = bool(flags & (1 << 3))
        question_str = String.read(b)
        question = raw.types.TextWithEntities(text=question_str, entities=[])
        answers = TLObject.read(b)
        close_period = Int.read(b) if flags & (1 << 4) else None
        close_date = Int.read(b) if flags & (1 << 5) else None
        return raw.types.Poll(
            id=poll_id,
            question=question,
            answers=answers,
            closed=closed,
            public_voters=public_voters,
            multiple_choice=multiple_choice,
            quiz=quiz,
            close_period=close_period,
            close_date=close_date,
        )


class _LegacyPollAnswer(TLObject):
    __slots__ = ["added_by", "date", "media", "option", "text"]
    ID = 0x6ca9c2e9
    QUALNAME = "types.PollAnswer"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PollAnswer:
        text_str = String.read(b)
        text = raw.types.TextWithEntities(text=text_str, entities=[])
        option = Bytes.read(b)
        return raw.types.PollAnswer(text=text, option=option)


class _LegacyPollResults(TLObject):
    __slots__ = [
        "can_view_stats",
        "has_unread_votes",
        "min",
        "recent_voters",
        "results",
        "solution",
        "solution_entities",
        "solution_media",
        "total_voters",
    ]
    ID = 0xdcb82ea3
    QUALNAME = "types.PollResults"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.PollResults:
        flags = Int.read(b)
        min_flag = bool(flags & (1 << 0))
        results = TLObject.read(b) if flags & (1 << 1) else None
        total_voters = Int.read(b) if flags & (1 << 2) else None
        _recent = TLObject.read(b) if flags & (1 << 3) else None
        solution = String.read(b) if flags & (1 << 4) else None
        solution_entities = TLObject.read(b) if flags & (1 << 4) else None
        return raw.types.PollResults(
            min=min_flag,
            results=results,
            total_voters=total_voters,
            solution=solution,
            solution_entities=solution_entities,
        )


class _LegacyBotInfo(TLObject):
    __slots__ = [
        "app_settings",
        "commands",
        "description",
        "description_document",
        "description_photo",
        "has_preview_medias",
        "menu_button",
        "privacy_policy_url",
        "user_id",
        "verifier_settings",
    ]
    ID = 0x8f300b57
    QUALNAME = "types.BotInfo"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.BotInfo:
        flags = Int.read(b)
        user_id = Long.read(b) if flags & (1 << 0) else None
        description = String.read(b) if flags & (1 << 1) else None
        description_photo = TLObject.read(b) if flags & (1 << 4) else None
        description_document = TLObject.read(b) if flags & (1 << 5) else None
        commands = TLObject.read(b) if flags & (1 << 2) else None
        menu_button = TLObject.read(b) if flags & (1 << 3) else None
        return raw.types.BotInfo(
            user_id=user_id,
            description=description,
            description_photo=description_photo,
            description_document=description_document,
            commands=commands,
            menu_button=menu_button,
        )


class _LegacyBotCommand(TLObject):
    __slots__ = ["command", "description", "ephemeral"]
    ID = 0xc27ac8c7
    QUALNAME = "types.BotCommand"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.BotCommand:
        cmd = String.read(b)
        desc = String.read(b)
        return raw.types.BotCommand(command=cmd, description=desc)


class _LegacyEmojiStatus(TLObject):
    __slots__ = ["document_id", "until"]
    ID = 0x929b619d
    QUALNAME = "types.EmojiStatus"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.EmojiStatus:
        document_id = Long.read(b)
        return raw.types.EmojiStatus(document_id=document_id)


class _LegacyForumTopic(TLObject):
    __slots__ = [
        "closed",
        "date",
        "draft",
        "from_id",
        "hidden",
        "icon_color",
        "icon_emoji_id",
        "id",
        "my",
        "notify_settings",
        "peer",
        "pinned",
        "read_inbox_max_id",
        "read_outbox_max_id",
        "short",
        "title",
        "title_missing",
        "top_message",
        "unread_count",
        "unread_mentions_count",
        "unread_poll_votes_count",
        "unread_reactions_count",
    ]
    ID = 0x71701da9
    QUALNAME = "types.ForumTopic"

    @staticmethod
    def read(b: BytesIO, *args: Any) -> raw.types.ForumTopic:
        flags = Int.read(b)
        my = bool(flags & (1 << 1))
        closed = bool(flags & (1 << 2))
        pinned = bool(flags & (1 << 3))
        short = bool(flags & (1 << 5))
        hidden = bool(flags & (1 << 6))
        topic_id = Int.read(b)
        date = Int.read(b)
        title = String.read(b)
        icon_color = Int.read(b)
        icon_emoji_id = Long.read(b) if flags & (1 << 0) else None
        top_message = Int.read(b)
        read_inbox_max_id = Int.read(b)
        read_outbox_max_id = Int.read(b)
        unread_count = Int.read(b)
        unread_mentions_count = Int.read(b)
        unread_reactions_count = Int.read(b)
        from_id = TLObject.read(b)
        notify_settings = TLObject.read(b)
        draft = TLObject.read(b) if flags & (1 << 4) else None
        return raw.types.ForumTopic(
            id=topic_id,
            date=date,
            peer=from_id,
            title=title,
            icon_color=icon_color,
            top_message=top_message,
            read_inbox_max_id=read_inbox_max_id,
            read_outbox_max_id=read_outbox_max_id,
            unread_count=unread_count,
            unread_mentions_count=unread_mentions_count,
            unread_reactions_count=unread_reactions_count,
            from_id=from_id,
            notify_settings=notify_settings,
            my=my,
            closed=closed,
            pinned=pinned,
            short=short,
            hidden=hidden,
            icon_emoji_id=icon_emoji_id,
            draft=draft,
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
    _LegacyWebPageEmpty,
    _LegacyWebPagePending,
    _LegacyUpdateUserTyping,
    _LegacyUpdateReadHistoryInbox,
    _LegacyUpdateReadMessagesContents,
    _LegacyUpdateDraftMessage,
    _LegacyUpdateChannelReadMessagesContents,
    _LegacyUpdateDialogUnreadMark,
    _LegacyUpdateMessagePoll,
    _LegacyUpdateMessagePollVote,
    _LegacyUpdateDeleteScheduledMessages,
    _LegacyUpdatePeerBlocked,
    _LegacyUpdateMessageReactions,
    _LegacyUpdateMessageExtendedMedia,
    _LegacyMessageFwdHeader,
    _LegacyMessageReplyHeader,
    _LegacyMessageMediaPhoto,
    _LegacyMessageMediaDocument,
    _LegacyMessageMediaDice,
    _LegacyMessageMediaPoll,
    _LegacyMessageReactions,
    _LegacyDraftMessage,
    _LegacyPoll,
    _LegacyPollAnswer,
    _LegacyPollResults,
    _LegacyBotInfo,
    _LegacyBotCommand,
    _LegacyEmojiStatus,
    _LegacyForumTopic,
)


def register_legacy_types() -> None:
    for cls in _LEGACY_TYPES:
        raw.all.objects[cls.ID] = cls
        raw.core.tl_object.objects[cls.ID] = cls

