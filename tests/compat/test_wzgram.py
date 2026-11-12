# внутренности wzgram, на которые опирается ядро. падает первым при обновлении wzgram.

import inspect
from types import SimpleNamespace

import pyrogram
import pytest
from pyrogram import raw
from pyrogram.dispatcher import Dispatcher
from pyrogram.enums import ParseMode

from elys.core import clients
from elys.core.clients import ElysClient, NotLoggedIn
from elys.core.gate import GateDispatcher
from elys.settings import Settings
from tests import factories as f


def test_version_pinned():
    assert pyrogram.__version__ == "3.1.6"
    import wzgram

    assert wzgram is pyrogram


def test_message_update_groups():
    assert {raw.types.UpdateNewMessage, raw.types.UpdateNewChannelMessage} <= set(Dispatcher.NEW_MESSAGE_UPDATES)
    assert {raw.types.UpdateEditMessage, raw.types.UpdateEditChannelMessage} <= set(Dispatcher.EDIT_MESSAGE_UPDATES)


def test_parsers_flat_and_signature():
    dispatcher = Dispatcher(pyrogram.Client("t", api_id=1, api_hash="x", in_memory=True))
    for raw_type in (*Dispatcher.NEW_MESSAGE_UPDATES, *Dispatcher.EDIT_MESSAGE_UPDATES):
        parser = dispatcher.update_parsers[raw_type]
        assert inspect.iscoroutinefunction(parser)
        assert list(inspect.signature(parser).parameters) == ["update", "users", "chats"]


def test_worker_parses_before_handlers():
    source = inspect.getsource(Dispatcher.handler_worker)
    assert "self.update_parsers.get(type(update)" in source
    assert "await parser(update, users, chats)" in source


def test_short_branch_does_get_difference():
    source = inspect.getsource(pyrogram.Client.handle_updates)
    assert "UpdateShortMessage, raw.types.UpdateShortChatMessage" in source
    assert "GetDifference" in source
    assert list(inspect.signature(pyrogram.Client._save_update_state).parameters) == ["self", "state"]


def test_update_watchdog_fields():
    # клиент обновляет их сам, когда режет короткий апдейт: иначе watchdog решит, что связь пропала
    source = inspect.getsource(pyrogram.Client)
    assert "self._last_update_monotonic = time.monotonic()" in source
    assert "time.monotonic() - self._last_update_monotonic" in source
    assert "self.last_update_time = datetime.now()" in source


def test_message_parse_respects_fetch_flags():
    source = inspect.getsource(inspect.getmodule(pyrogram.types.Message))
    assert "elif client.fetch_replies and not parsed_message.reply_to_message:" in source
    assert "client.fetch_topics and client.me" in source


def test_listener_registry_is_falsy_when_empty():
    assert not pyrogram.Client("t", api_id=1, api_hash="x", in_memory=True).listeners


def test_user_client_defaults(tmp_path):
    client = clients.user(Settings(api_id=1, api_hash="x", data_dir=tmp_path), version="t")
    assert isinstance(client.dispatcher, GateDispatcher)
    assert client.gate.listeners is client.listeners
    assert not (client.fetch_replies or client.fetch_topics or client.fetch_stories or client.fetch_stickers)
    assert client.skip_updates and client.auto_no_updates
    assert client.parse_mode is ParseMode.HTML
    assert client.rate_limiter is not None
    assert client.workdir == tmp_path


class Recorder:
    def __init__(self):
        self.invoked, self.states, self.enqueued = [], [], []

    def attach(self, client):
        async def invoke(query, *a, **kw):
            self.invoked.append(type(query).__name__)
            return SimpleNamespace(new_messages=[], other_updates=[], users=[], chats=[])

        async def update_state(state):
            self.states.append(state)

        async def enqueue(*args):
            self.enqueued.append(args)

        client.invoke = invoke
        client.storage.update_state = update_state
        client.dispatcher.enqueue_update = enqueue
        return self


def make(cls):
    return cls("t", api_id=1, api_hash="x", in_memory=True)


async def test_plain_client_pays_rpc_for_short_message():
    client = make(pyrogram.Client)
    recorder = Recorder().attach(client)
    await client.handle_updates(f.short_private(5))
    assert recorder.invoked == ["GetDifference"]


async def test_gated_short_message_saves_pts_without_rpc():
    client = make(ElysClient)
    recorder = Recorder().attach(client)
    await client.handle_updates(f.short_private(5, pts=77))
    assert recorder.invoked == []
    assert recorder.states == [(0, 77, None, 100, None)]
    assert client._last_update_monotonic > 0 and client.last_update_time is not None


async def test_own_short_message_goes_through():
    client = make(ElysClient)
    recorder = Recorder().attach(client)
    await client.handle_updates(f.short_private(5, out=True))
    assert recorder.invoked == ["GetDifference"]


async def test_run_without_session_does_not_prompt():
    with pytest.raises(NotLoggedIn):
        await make(ElysClient).authorize()


@pytest.mark.parametrize("failure", ["cancel", "exit"])
async def test_interrupted_start_disconnects(failure):
    import asyncio
    from unittest.mock import AsyncMock

    client = make(ElysClient)

    async def connect():
        client.is_connected = True
        return False

    async def authorize():
        if failure == "cancel":
            raise asyncio.CancelledError
        raise SystemExit("login aborted")

    client.connect = connect
    client.authorize = authorize
    client.disconnect = AsyncMock()
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else SystemExit):
        await client.start()
    client.disconnect.assert_awaited_once()


async def test_repeated_start_does_not_disconnect_running_client():
    from unittest.mock import AsyncMock

    client = make(ElysClient)
    client.is_connected = True
    client.disconnect = AsyncMock()
    with pytest.raises(ConnectionError):
        await client.start()
    client.disconnect.assert_not_awaited()
    assert client.is_connected


async def test_file_session_is_private_even_when_login_fails(tmp_path):
    import os
    from unittest.mock import AsyncMock

    if os.name != "posix":
        pytest.skip("POSIX permissions")
    client = clients.user(Settings(api_id=1, api_hash="h", data_dir=tmp_path), version="t")

    async def connect():
        await client.storage.open()
        client.is_connected = True
        return False

    async def disconnect():
        await client.storage.close()
        client.is_connected = False

    client.connect = connect
    client.disconnect = disconnect
    client.authorize = AsyncMock(side_effect=NotLoggedIn)
    with pytest.raises(NotLoggedIn):
        await client.start()
    assert tmp_path.stat().st_mode & 0o777 == 0o700
    assert client.storage.database.stat().st_mode & 0o777 == 0o600


def test_legacy_reply_inline_markup_deserialization():
    from io import BytesIO

    from pyrogram import types
    from pyrogram.raw.core import TLObject
    from pyrogram.raw.core.primitives import Bytes, Int, String, Vector

    # проверяем десериализацию старого replyInlineMarkup (0x48a30254)
    # со старыми кнопками keyboardButtonUrl (0xd80c25ec) и keyboardButtonCallback (0xe62bc960)
    btn1 = BytesIO()
    btn1.write(Int(0xD80C25EC, False))  # keyboardButtonUrl
    btn1.write(Int(0))  # flags (no style)
    btn1.write(String("Link"))
    btn1.write(String("https://example.com"))

    btn2 = BytesIO()
    btn2.write(Int(0xE62BC960, False))  # keyboardButtonCallback
    btn2.write(Int(0))  # flags
    btn2.write(String("Callback"))
    btn2.write(Bytes(b"cb_data"))

    row_bytes = BytesIO()
    row_bytes.write(Int(0x77608B83, False))  # keyboardButtonRow
    row_bytes.write(Vector([TLObject.read(BytesIO(btn1.getvalue())), TLObject.read(BytesIO(btn2.getvalue()))]))

    b = BytesIO()
    b.write(Int(0x48A30254, False))  # replyInlineMarkup
    b.write(Vector([TLObject.read(BytesIO(row_bytes.getvalue()))]))
    b.seek(0)

    res = TLObject.read(b)
    assert isinstance(res, raw.types.ReplyInlineMarkup)
    assert len(res.rows) == 1

    parsed = types.InlineKeyboardMarkup.read(res)
    assert len(parsed.inline_keyboard[0]) == 2
    assert parsed.inline_keyboard[0][0].text == "Link"
    assert parsed.inline_keyboard[0][0].url == "https://example.com"
    assert parsed.inline_keyboard[0][1].text == "Callback"
    assert parsed.inline_keyboard[0][1].callback_data == "cb_data"
