# raw-объекты для тестов гейта.

from time import time

from pyrogram import raw

T = raw.types


def message(peer, *, out=False, from_id=None, text="hi", id=1, **kw):
    return T.Message(id=id, peer_id=peer, date=0, message=text, out=out, from_id=from_id, **kw)


def new(msg):
    return T.UpdateNewMessage(message=msg, pts=1, pts_count=1)


def new_channel(msg):
    return T.UpdateNewChannelMessage(message=msg, pts=1, pts_count=1)


def edit(msg, *, fresh=True):
    # по умолчанию — настоящая правка «сейчас»; fresh=False без edit_date — как реакция на сообщение
    msg.edit_date = msg.edit_date or (int(time()) if fresh else None)
    return T.UpdateEditMessage(message=msg, pts=1, pts_count=1)


def short_private(user_id, *, out=False, pts=10):
    return T.UpdateShortMessage(id=1, user_id=user_id, message="hi", pts=pts, pts_count=1, date=100, out=out)


def short_chat(chat_id, from_id, *, out=False, pts=10):
    return T.UpdateShortChatMessage(
        id=1, from_id=from_id, chat_id=chat_id, message="hi", pts=pts, pts_count=1, date=100, out=out
    )


def channel(id, *, broadcast):
    return T.Channel(id=id, title="c", photo=T.ChatPhotoEmpty(), date=0, broadcast=broadcast, megagroup=not broadcast)
