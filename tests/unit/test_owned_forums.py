from types import SimpleNamespace

from pyrogram import raw

from elys.core.clients import ElysClient


def channel(identity, title="Elys", *, forum=True, creator=True):
    return raw.types.Channel(id=identity, title=title, photo=raw.types.ChatPhotoEmpty(), date=1,
                             forum=forum or None, creator=creator or None, megagroup=True)


def dialog(identity):
    return raw.types.Dialog(
        peer=raw.types.PeerChannel(channel_id=identity), top_message=identity, read_inbox_max_id=0,
        read_outbox_max_id=0, unread_count=0, unread_mentions_count=0, unread_reactions_count=0,
        unread_poll_votes_count=0, notify_settings=raw.types.PeerNotifySettings())


def message(identity):
    return raw.types.Message(id=identity, peer_id=raw.types.PeerChannel(channel_id=identity), date=identity,
                             message="text")


def page(*chats):
    ids = [chat.id for chat in chats]
    return raw.types.messages.Dialogs(
        dialogs=[dialog(i) for i in ids], messages=[message(i) for i in ids], chats=list(chats), users=[])


async def test_owned_forums_reads_only_chats_paginates_and_filters():
    pages = [
        page(channel(1), channel(2, creator=False), channel(3, "Другой"), channel(4, forum=False), channel(5)),
        page(channel(6), channel(1)),
        page(),
    ]
    requests = []

    async def invoke(request, **kwargs):
        requests.append(request)
        return pages[len(requests) - 1]

    async def resolve_peer(peer_id):
        return peer_id

    fake = SimpleNamespace(invoke=invoke, resolve_peer=resolve_peer)
    found = await ElysClient.owned_forums(fake, "Elys")
    # дубли оставляет вызывающий код (dict.fromkeys), порядок — как в списке диалогов
    assert found == [-1000000000001, -1000000000005, -1000000000006, -1000000000001]
    # следующая страница начинается после последнего диалога предыдущей
    assert requests[1].offset_id == 5 and requests[1].offset_date == 5 and requests[1].offset_peer == -1000000000005
    assert len(requests) == 3
