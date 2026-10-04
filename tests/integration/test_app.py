import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram.types import User

from elys import Module
from elys import app as app_module
from elys.app import App
from elys.core.gate import Gate
from elys.settings import Settings
from elys.storage.kv import KV


@pytest.mark.parametrize("cancel_unload", [False, True])
async def test_lifecycle_flushes_hooks_and_closes_every_module(tmp_path, monkeypatch, cancel_unload):
    events = []

    async def start():
        events.append("start")

    async def stop():
        events.append("stop")

    async def idle():
        events.append("idle")

    client = SimpleNamespace(
        start=start, stop=stop, me=User(id=1, first_name="Test"), gate=Gate(),
        add_handler=lambda *args: None,
    )
    monkeypatch.setattr(app_module.clients, "user", lambda *args, **kwargs: client)
    monkeypatch.setattr(app_module, "idle", idle)
    first, second = Module("first"), Module("second")

    @first.on_load
    async def loaded(client):
        events.append("load")
        first.db["loaded"] = True

    @first.on_unload
    async def save(client):
        events.append("unload first")
        first.db["saved"] = True

    @second.on_unload
    async def unload(client):
        events.append("unload second")
        if cancel_unload:
            raise asyncio.CancelledError

    monkeypatch.setattr(app_module.builtin, "NAMES", ("first", "second"))
    monkeypatch.setattr(app_module, "import_module", lambda name: SimpleNamespace(module={
        "first": first, "second": second,
    }[name.rsplit(".", 1)[-1]]))
    async def bot_start():
        events.append("bot start")
        app.bot = SimpleNamespace()

    async def bot_stop():
        events.append("bot stop")

    async def ensure_forum():
        events.append("forum")
        return SimpleNamespace(send=AsyncMock())

    async def inline_start():
        events.append("inline start")

    async def inline_stop():
        events.append("inline stop")

    monkeypatch.setattr(app_module, "BotService", lambda app: SimpleNamespace(start=bot_start, stop=bot_stop))
    monkeypatch.setattr(app_module, "Forum", lambda app: SimpleNamespace(ensure=ensure_forum, send=AsyncMock()))
    monkeypatch.setattr(app_module, "Inline", lambda app: SimpleNamespace(
        start=inline_start, close=inline_stop, units=SimpleNamespace(remove_owner=lambda owner: None)))
    app = App(Settings(api_id=1, api_hash="h", data_dir=tmp_path))
    if cancel_unload:
        with pytest.raises(asyncio.CancelledError):
            await app.run()
    else:
        await app.run()
    assert events == ["start", "bot start", "forum", "inline start", "load", "idle",
                      "unload second", "unload first", "inline stop", "bot stop", "stop"]
    assert app.modules == {}
    assert not first.loaded and not second.loaded
    assert not client.gate.matcher
    assert app.router.get("ping") is None
    with pytest.raises(RuntimeError, match="закрыт"):
        app.kv.ns("core")
    kv = await KV.open(tmp_path / "elys.db")
    assert dict(kv.ns("mod:first")) == {"loaded": True, "saved": True}
    await kv.close()
