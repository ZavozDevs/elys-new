import asyncio
from importlib import import_module
from types import SimpleNamespace

import pytest

from elys import Config, Module, respond
from elys.sdk.module import LoadError
from tests.integration.test_loader import app as app
from tests.integration.test_loader import source as source


class Msg(SimpleNamespace):
    def __init__(self, text, *, outgoing=True):
        super().__init__(text=text, caption=None, outgoing=outgoing, command=None, chat=None,
                         reply_to_message=None, reply_to_message_id=None, edits=[], options=[])

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)
        self.options.append(kwargs)
        return self


async def invoke(app, text, *, outgoing=True):
    message = Msg(text, outgoing=outgoing)
    await app.router.dispatch(app.client, message)
    command = app.router.get(message.command[0]) if message.command else None
    if command:
        await asyncio.gather(*tuple(command.owner._resources.tasks))
    return message


async def setup(app):
    for name in ("help", "modman", "prefs", "ping"):
        await app.load(import_module(f"elys.builtin.{name}").module)


async def test_help_settings_alias_and_owner_only_flow(app):
    await setup(app)
    help_message = await invoke(app, ".help")
    assert "Команда — обычное сообщение" in help_message.edits[0]
    assert ".dlm" in help_message.edits[0]
    detail = await invoke(app, ".help Ping")
    assert "задержка ответа telegram" in detail.edits[0]
    await invoke(app, ".prefs prefix !")
    await invoke(app, "!prefs alias п ping")
    ping = await invoke(app, "!п")
    assert "Понг" in ping.edits[-1]
    assert (await invoke(app, "!п", outgoing=False)).edits == []
    assert (await invoke(app, ".ping")).edits == []
    assert app.kv.ns("core")["prefixes"] == ["!"]
    assert app.kv.ns("core")["aliases"] == {"п": "ping"}
    await invoke(app, "!prefs unalias п")
    assert app.router.get("п") is None
    await invoke(app, "!prefs language en")
    assert "your account assistant" in (await invoke(app, "!help")).edits[0]
    await invoke(app, "!prefs banners off")
    assert app.banners_enabled is False


async def test_dlm_requires_trust_and_unload_purge_requires_confirmation(app, source):
    await setup(app)
    response = await invoke(app, f".dlm {source}")
    assert "доступ к аккаунту" in response.edits[0]
    assert "Hello" not in app.modules
    await invoke(app, f".dlm {source} --trust")
    assert "Hello" in app.modules
    # фоновые задачи стороннего модуля не мешают завершить команду управления.
    response = await invoke(app, ".ulm Hello --purge")
    assert "--yes" in response.edits[0]
    assert "Hello" in app.modules
    await invoke(app, ".ulm Hello --purge --yes")
    assert "Hello" not in app.modules
    await invoke(app, ".lm hello")
    assert "Hello" in app.modules
    response = await invoke(app, ".ulm Help")
    assert "встроенный" in response.edits[0]


async def test_banner_context_and_live_premium_update(app):
    module = Module("Display", config=Config(banner=Config.url("https://example.org/banner.png")))

    @module.command("display")
    async def display(client, message):
        from elys import E
        await respond(message, E.check, banner=module.config["banner"])

    await app.load(module)
    message = await invoke(app, ".display")
    assert message.edits == ["✅"]
    preview = message.options[0]["link_preview_options"]
    assert preview.url == "https://example.org/banner.png" and preview.show_above_text
    app.premium = True
    app.banners_enabled = False
    message = await invoke(app, ".display")
    assert "tg-emoji" in message.edits[0]
    assert message.options[0]["link_preview_options"].is_disabled


async def test_loops_raw_deleted_ready_and_bot_decorators(app):
    module = Module("SDK")
    calls = []

    @module.on_raw_update()
    async def raw(client, update, users, chats):
        calls.append("raw")

    @module.on_deleted_messages()
    async def deleted(client, messages):
        calls.append("deleted")

    @module.loop(60)
    async def loop(client):
        calls.append("loop")

    await app.load(module)
    assert not app.client.gate.matcher
    for _, handler in module._resources.handlers:
        await handler.callback(app.client, *(({}, {}, {}) if handler.callback.__name__ == "raw" else ([],)))
    first = loop.start()
    assert loop.start() is first
    await asyncio.sleep(0)
    await loop.stop()
    assert first.cancelled()
    assert calls == ["raw", "deleted", "loop"]
    await app.unload("SDK")
    bot_module = Module("Bot")

    @bot_module.callback("weather:")
    async def callback(client, query):
        calls.append("callback")

    @bot_module.inline("weather")
    async def inline(client, query):
        calls.append("inline")

    with pytest.raises(LoadError, match="этапе 3"):
        await app.load(bot_module)
    assert not app.registry.entries
    app.bot = app.client
    await app.load(bot_module)
    for _, handler in bot_module._resources.handlers:
        query = SimpleNamespace(data="weather:refresh", query="weather")
        assert await handler.check(app.bot, query)
        await handler.callback(app.bot, query)
        assert not await handler.check(app.bot, SimpleNamespace(data="other", query="other"))
    await app.unload("Bot")
    assert not app.client.dispatcher.groups
    assert calls[-2:] == ["callback", "inline"]


async def test_bad_alias_is_user_error_not_internal_failure(app):
    await setup(app)
    response = await invoke(app, ".prefs alias ping help")
    assert response.edits[0].startswith("🚫 ")
    assert "занята" in response.edits[0] and "Примеры: .prefs" in response.edits[0]
    assert "Команда не сработала" not in response.edits[0]
    assert app.router.get("ping").owner.name == "Ping"


async def test_documented_example_and_roles_are_owner_only(app):
    item = await app.loader.install("examples/hello.py", trusted=True)
    response = await invoke(app, ".hello <Маша>")
    assert response.edits == ["✅ Привет, &lt;Маша&gt;!"]
    item.config["greeting"] = "Добрый день"
    await app.loader.reload("Hello")
    response = await invoke(app, ".привет Мир")
    assert response.edits == ["✅ Добрый день, Мир!"]
    roles = Module("Roles")

    @roles.command("restricted", roles={"sudo"})
    async def restricted(client, message):
        await respond(message, "owner")

    await app.load(roles)
    assert app.router.get("restricted").roles == {"sudo"}
    assert (await invoke(app, ".restricted", outgoing=False)).edits == []
    assert (await invoke(app, ".restricted")).edits == ["owner"]
