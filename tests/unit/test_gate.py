import pyrogram
import pytest
from pyrogram import raw

from elys.core.gate import Gate, GateDispatcher
from elys.core.scope import Scope
from tests import factories as f

T = raw.types
CHAT = T.PeerChat(chat_id=7)
CHANNEL_ID = 100500
CHANNEL = T.PeerChannel(channel_id=CHANNEL_ID)


def gate(*scopes, listeners=()):
    g = Gate(listeners)
    g.rebuild(s.default_kind(edited=False) for s in scopes)
    return g


def test_closed_gate_drops_incoming_passes_own():
    g = gate()
    assert not g(f.new(f.message(T.PeerUser(user_id=5))), {})
    assert g(f.new(f.message(T.PeerUser(user_id=5), out=True)), {})


def test_active_listener_opens_everything():
    assert gate(listeners=[object()])(f.new(f.message(CHAT, from_id=T.PeerUser(user_id=5))), {})


def test_incoming_sender_does_not_bypass_scope():
    g = gate(Scope.PRIVATE)
    assert g(f.new(f.message(T.PeerUser(user_id=5))), {})
    assert not g(f.new(f.message(CHAT, from_id=T.PeerUser(user_id=5))), {})
    assert not g(f.new(f.message(CHAT, from_id=T.PeerUser(user_id=6))), {})


def test_scope_chat_type():
    g = gate(Scope.PRIVATE)
    assert g(f.new(f.message(T.PeerUser(user_id=5))), {})
    assert not g(f.new(f.message(CHAT, from_id=T.PeerUser(user_id=5))), {})


@pytest.mark.parametrize(("broadcast", "passes"), [(True, True), (False, False)])
def test_channel_vs_megagroup(broadcast, passes):
    chats = {CHANNEL_ID: f.channel(CHANNEL_ID, broadcast=broadcast)}
    assert gate(Scope.CHANNEL)(f.new_channel(f.message(CHANNEL)), chats) is passes


def test_scope_chats_uses_bot_api_ids():
    g = gate(Scope.chats({-1_000_000_000_000 - CHANNEL_ID, -7}))
    assert g(f.new_channel(f.message(CHANNEL)), {})
    assert g(f.new(f.message(CHAT, from_id=T.PeerUser(user_id=1))), {})
    assert not g(f.new(f.message(T.PeerUser(user_id=7))), {})


def test_edits_need_edited_scope():
    msg = f.message(T.PeerUser(user_id=5))
    assert not gate(Scope.PRIVATE)(f.edit(msg), {}, True)
    assert gate(Scope.PRIVATE | Scope.EDITED)(f.edit(msg), {}, True)


def test_message_empty_dropped():
    assert not gate(Scope.ALL)(f.new(T.MessageEmpty(id=1)), {})


def test_short_updates():
    g = gate(Scope.GROUP)
    assert g.short(f.short_private(5, out=True))
    assert not g.short(f.short_private(9))
    assert not g.short(f.short_private(5))
    assert g.short(f.short_chat(7, 5))
    assert gate(Scope.chats({-7})).short(f.short_chat(7, 5))
    assert not gate(Scope.chats({7})).short(f.short_chat(7, 5))
    assert gate(listeners=[1]).short(f.short_private(5))


async def test_dispatcher_wraps_message_parsers(monkeypatch):
    parsed = object()

    async def fake_parse(*args, **kwargs):
        return parsed

    monkeypatch.setattr(pyrogram.types.Message, "_parse", fake_parse)
    client = pyrogram.Client("t", api_id=1, api_hash="x", in_memory=True)
    dispatcher = GateDispatcher(client, gate())
    for raw_type in (*dispatcher.NEW_MESSAGE_UPDATES, *dispatcher.EDIT_MESSAGE_UPDATES):
        assert dispatcher.update_parsers[raw_type].__qualname__.startswith("_gated")

    parse = dispatcher.update_parsers[T.UpdateNewMessage]
    assert await parse(f.new(f.message(T.PeerUser(user_id=5))), {}, {}) == (None, type(None))
    result, handler = await parse(f.new(f.message(T.PeerUser(user_id=5), out=True)), {}, {})
    assert result is parsed
    assert handler is pyrogram.handlers.MessageHandler
