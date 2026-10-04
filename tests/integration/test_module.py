import asyncio
from types import SimpleNamespace

import pytest
from pyrogram import filters

from elys import Module, Scope, UserError
from elys.core.router import Router
from elys.core.scope import PRIVATE, key
from elys.sdk.module import LoadError, find
from elys.storage.kv import KV


class FakeClient:
    def __init__(self):
        self.handlers = []
        self.me = None

    def add_handler(self, handler, group):
        self.handlers.append((handler, group))

    def remove_handler(self, handler, group):
        self.handlers.remove((handler, group))


class Msg(SimpleNamespace):
    async def edit_text(self, text, **kwargs):
        self.edits.append(text)
        return self


@pytest.fixture
async def host(tmp_path):
    kv = await KV.open(tmp_path / "db", delay=60)
    yield SimpleNamespace(client=FakeClient(), router=Router(["."]), kv=kv)
    await kv.close()


def make():
    module = Module("Test")
    events = []

    @module.command("ok", aliases=["o"])
    async def ok(client, message):
        events.append(message.command)

    @module.command("bad")
    async def bad(client, message):
        raise UserError("плохо")

    @module.command("boom")
    async def boom(client, message):
        raise ZeroDivisionError("x")

    @module.on_message(filters.private, scope=Scope.PRIVATE | Scope.INCOMING)
    async def watcher(client, message):
        events.append("watch")

    @module.on_load
    async def loaded(client):
        events.append("load")

    @module.on_unload
    async def unloaded(client):
        events.append("unload")

    return module, events


async def command(host, text):
    message = Msg(text=text, caption=None, chat=None, outgoing=True, command=None, edits=[])
    await host.router.dispatch(host.client, message)
    await asyncio.sleep(0)
    return message


async def test_attach_detach_lifecycle(host):
    module, events = make()
    await module.attach(host, group=3)
    assert module.loaded
    assert events == ["load"]
    assert [g for _, g in host.client.handlers] == [3]
    assert module.scopes[0].keys() == {key(PRIVATE)}
    assert module.db is host.kv.ns("mod:Test")

    await command(host, ".o 1")
    assert events[-1] == ["ok", "1"]

    sleeper = module.spawn(asyncio.sleep(60))
    await module.detach()
    assert sleeper.cancelled()
    assert events[-1] == "unload"
    assert host.client.handlers == []
    assert host.router.get("ok") is None
    with pytest.raises(RuntimeError):
        module.spawn(asyncio.sleep(0))


async def test_errors_are_reported(host):
    module, _ = make()
    await module.attach(host, group=0)
    assert (await command(host, ".bad")).edits == ["🚫 плохо"]
    edits = (await command(host, ".boom")).edits
    assert "Команда не сработала" in edits[0]
    assert "ZeroDivisionError: x" in edits[0]
    await module.detach()


async def test_command_is_logged_and_error_has_id(host, caplog):
    module, _ = make()
    await module.attach(host, group=0)
    with caplog.at_level("INFO"):
        await command(host, ".o 1")
        edits = (await command(host, ".boom")).edits
    await module.detach()
    done = [r for r in caplog.records if r.name == "elys.cmd"]
    assert len(done) == 1 and done[0].mark == "cmd" and done[0].getMessage().startswith(".o ")
    failed = next(r for r in caplog.records if r.name == "elys.mod.Test")
    assert f"#{failed.error_id}" in edits[0]


async def test_unloaded_watcher_is_silent(host):
    module, events = make()
    await module.attach(host, group=0)
    handler = host.client.handlers[0][0]
    await module.detach()
    await handler.callback(None, None)  # апдейт, пришедший после асинхронного remove_handler
    assert "watch" not in events


async def test_failed_on_load_rolls_back(host):
    module = Module("Broken")

    @module.command("x")
    async def x(client, message): ...

    @module.on_load
    async def fail(client):
        raise RuntimeError

    with pytest.raises(RuntimeError):
        await module.attach(host, group=0)
    assert not module.loaded
    assert host.router.get("x") is None


def test_listens_all_flag():
    module = Module("All")

    @module.on_message()
    async def everything(client, message): ...

    assert module.listens_all
    assert make()[0].listens_all is False


def test_find():
    module = Module("One")
    assert find({"m": module, "x": 1}, "one") is module
    with pytest.raises(LoadError):
        find({}, "none")


async def test_welcome_is_shown_once_in_terminal(host, caplog):
    from elys.builtin.welcome import module as welcome

    sent = []

    async def send_message(chat_id, text):
        sent.append((chat_id, text))

    host.client.send_message = send_message
    with caplog.at_level("INFO", logger="elys.mod.Welcome"):
        await welcome.attach(host, group=0)
        await welcome.detach()
        await welcome.attach(host, group=0)
        await welcome.detach()
    shown = [r.getMessage() for r in caplog.records if r.name == "elys.mod.Welcome"]
    assert len(shown) == 1
    assert "напиши .ping" in shown[0]
    assert sent == []  # в «Избранное» и вообще в чаты не пишем


async def test_double_attach_does_not_corrupt_registration(host):
    module, _ = make()
    await module.attach(host, group=1)
    with pytest.raises(RuntimeError, match="уже загружен"):
        await module.attach(host, group=2)
    assert len(host.client.handlers) == 1
    await module.detach()
    assert host.client.handlers == []
    assert host.router.get("ok") is None


async def test_failed_handler_registration_rolls_back(host):
    module, _ = make()

    @module.on_message(scope=Scope.ALL)
    async def second(client, message): ...

    add = host.client.add_handler

    def fail_second(handler, group):
        if host.client.handlers:
            raise RuntimeError("registration failed")
        add(handler, group)

    host.client.add_handler = fail_second
    with pytest.raises(RuntimeError, match="registration failed"):
        await module.attach(host, group=1)
    assert host.client.handlers == []
    assert host.router.get("ok") is None
    assert not module.loaded
    with pytest.raises(RuntimeError, match="не загружен"):
        _ = module.app


async def test_cancelled_unload_cleans_tasks_and_handlers(host):
    module, _ = make()

    @module.on_unload
    async def cancel(client):
        raise asyncio.CancelledError

    await module.attach(host, group=0)
    task = module.spawn(asyncio.sleep(60))
    with pytest.raises(asyncio.CancelledError):
        await module.detach()
    assert task.cancelled()
    assert host.client.handlers == []
    assert host.router.get("ok") is None
    for name in ("app", "client", "db"):
        with pytest.raises(RuntimeError, match="не загружен"):
            getattr(module, name)


async def test_user_error_is_plain_text(host):
    module = Module("Errors")

    @module.command("bad")
    async def bad(client, message):
        raise UserError("<b>не HTML</b> & текст")

    await module.attach(host, group=0)
    assert (await command(host, ".bad")).edits == ["🚫 &lt;b&gt;не HTML&lt;/b&gt; &amp; текст"]
    await module.detach()
