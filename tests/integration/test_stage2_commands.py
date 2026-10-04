import asyncio
from importlib import import_module
from types import SimpleNamespace

import pytest

from elys import Config, Module, respond
from elys.sdk.module import LoadError
from tests.inline_helpers import click, install_inline, last_unit
from tests.integration.test_loader import app as app
from tests.integration.test_loader import source as source


class Msg(SimpleNamespace):
    def __init__(self, text, *, outgoing=True):
        super().__init__(text=text, caption=None, outgoing=outgoing, command=None,
                         chat=SimpleNamespace(id=99, full_name="Chat"),
                         reply_to_message=None, reply_to_message_id=None, edits=[], options=[], deleted=False)

    async def delete(self, **kwargs):
        self.deleted = True

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
    install_inline(app)
    for name in ("help", "modman", "configure", "ping"):
        await app.load(import_module(f"elys.builtin.{name}").module)


async def test_help_settings_alias_and_owner_only_flow(app):
    await setup(app)
    help_message = await invoke(app, ".help")
    assert "Команда — обычное сообщение" in help_message.edits[0]
    assert ".dlm" in help_message.edits[0]
    detail = await invoke(app, ".help Ping")
    assert "задержка ответа telegram" in detail.edits[0]
    from elys.builtin.configure import apply_core
    apply_core(app, "prefixes", "!")
    apply_core(app, "aliases", "п ping")
    ping = await invoke(app, "!п")
    assert "Понг" in ping.edits[-1]
    assert (await invoke(app, "!п", outgoing=False)).edits == []
    assert (await invoke(app, ".ping")).edits == []
    assert app.kv.ns("core")["prefixes"] == ["!"]
    assert app.kv.ns("core")["aliases"] == {"п": "ping"}
    await invoke(app, "!config")
    unit = last_unit(app)
    await click(app, unit, "Настройки Elys")
    await click(app, unit, "Сокращения")
    await click(app, unit, "Удалить: п → ping")
    assert app.router.get("п") is None
    await click(app, unit, "‹ Назад")
    await click(app, unit, "Язык")
    await click(app, unit, "English")
    assert "your account assistant" in (await invoke(app, "!help")).edits[0]
    await click(app, unit, "‹ Назад")
    await click(app, unit, "Картинки над ответами")
    await click(app, unit, "Выключить")
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

    with pytest.raises(LoadError, match="бот-помощник"):
        await app.load(bot_module)
    assert not app.registry.entries
    app.bot = app.client
    await app.load(bot_module)
    for _, handler in bot_module._resources.handlers:
        query = SimpleNamespace(data="weather:refresh", query="weather", from_user=app.client.me)
        assert await handler.check(app.bot, query)
        await handler.callback(app.bot, query)
        assert not await handler.check(app.bot, SimpleNamespace(data="other", query="other", from_user=app.client.me))
    await app.unload("Bot")
    assert not app.client.dispatcher.groups
    assert calls[-2:] == ["callback", "inline"]


async def test_bad_alias_is_user_error_not_internal_failure(app):
    await setup(app)
    from elys.builtin.configure import apply_core
    with pytest.raises(ValueError, match="занята"):
        apply_core(app, "aliases", "ping help")
    assert app.router.get("ping").owner.name == "Ping"
    assert app.router.aliases == {}



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


async def test_config_cli_and_steppers_and_inline_query(app):
    await setup(app)
    custom = Module("Metrics", config=Config(
        count=Config.integer(5, min=0, max=20),
        tags=Config.series(["tag1", "tag2"], item_type=str),
    ))
    await app.load(custom)

    # 1. Быстрый CLI ввод
    cli_resp = await invoke(app, ".config Metrics count 12")
    assert "Metrics · count" in cli_resp.edits[0]
    assert custom.config["count"] == 12

    cli_core = await invoke(app, ".config core prefixes + =")
    assert "Начало команды" in cli_core.edits[0]
    assert app.router.prefixes == ("+", "=")

    # 2. UI меню и степперы
    await invoke(app, "+config Metrics count")
    unit = last_unit(app)
    assert "Сейчас: <code>12</code>" in unit.data["text"]

    await click(app, unit, "+1")
    assert custom.config["count"] == 13
    assert "Сейчас: <code>13</code>" in unit.data["text"]

    await click(app, unit, "-10")
    assert custom.config["count"] == 3
    assert "Сейчас: <code>3</code>" in unit.data["text"]

    # 3. Списки и удаление элементов
    await invoke(app, "+config Metrics tags")
    unit_tags = last_unit(app)
    assert "tag1" in unit_tags.data["text"]
    await click(app, unit_tags, "❌ tag1")
    assert custom.config["tags"] == ["tag2"]

    # 4. Inline query cfg со случайным 5-символьным токеном
    add_btn = next(b for row in unit_tags.data["markup"].inline_keyboard for b in row if b.text == "➕ Добавить")
    assert add_btn.switch_inline_query_current_chat.startswith("cfg ")
    token = add_btn.switch_inline_query_current_chat.split()[1]
    assert len(token) == 5

    q_token = SimpleNamespace(
        query=f"cfg {token} tag4",
        from_user=app.client.me,
        inline_message_id="msg-2",
    )
    from pyrogram import StopPropagation
    with pytest.raises(StopPropagation):
        await app.inline._chosen(app.bot, q_token)
    assert custom.config["tags"] == ["tag2", "tag4"]
