from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram import StopPropagation
from pyrogram.enums import ParseMode
from pyrogram.parser import Parser
from pyrogram.raw.types import MessageEntityCustomEmoji

from elys import Button, Config, Module, Photo
from elys.builtin import configure
from tests.inline_helpers import click, last_unit, query_for
from tests.integration.test_loader import app as app
from tests.integration.test_stage2_commands import invoke, setup


async def test_config_navigation_prefix_alias_persistence_and_secrets(app):
    await setup(app)
    item = Module("<Demo>", config=Config(
        count=Config.value(2, doc="Количество"), token=Config.secret("private-default", doc="Секрет"),
        enabled=Config.value(True, doc="Работать"), color=Config.choice("red", ["red", "blue"], doc="Цвет"),
    ))
    await app.load(item)
    assert app.router.get("prefs") is None
    await invoke(app, ".config")
    unit = last_unit(app)
    assert "Настройки модулей" in [b.text for b in unit.buttons.values()]
    await click(app, unit, "Настройки модулей")
    await click(app, unit, "<Demo>")
    await click(app, unit, "Секрет")
    assert "private-default" not in unit.data["text"]
    assert "Вернуть по умолчанию" not in [b.text for b in unit.buttons.values()]
    item.config["token"] = "changed"
    await click(app, unit, "‹ Назад")
    await click(app, unit, "Секрет")
    await click(app, unit, "Вернуть по умолчанию")
    await click(app, unit, "Вернуть по умолчанию")
    assert item.config["token"] == "private-default"
    await click(app, unit, "‹ Назад")
    await click(app, unit, "Работать")
    await click(app, unit, "Выключить")
    assert item.config["enabled"] is False
    await click(app, unit, "‹ Назад")
    await click(app, unit, "Цвет")
    await click(app, unit, "blue")
    assert item.config["color"] == "blue"
    parsed = await Parser(None).parse(unit.data["text"], mode=ParseMode.HTML)
    assert "<Demo>" in parsed["message"]
    await app.unload(item.name)
    await click(app, unit, "‹ Назад")
    assert "Настройки модулей" in unit.data["text"]
    assert not app.kv.ns("cfg:<Demo>")["enabled"]


async def test_routing_rejects_other_users_stale_buttons_and_expired_units(app):
    await setup(app)
    await invoke(app, ".config")
    unit = last_unit(app)
    denied = query_for(unit, "Настройки Elys", user_id=999)
    with pytest.raises(StopPropagation):
        await app.inline._callback(app.bot, denied)
    assert "владельцу" in denied.answer.call_args.args[0]
    assert "Elys · настройки" in unit.data["text"]
    stale = query_for(unit, "Настройки Elys")
    await click(app, unit, "Настройки Elys")
    await app.inline._run(unit, stale, int(stale.data.split(":")[1]))
    assert "изменился" in stale.answer.call_args.args[0]
    unit.expires = 0
    with pytest.raises(StopPropagation):
        await app.inline._callback(app.bot, stale)
    assert "устарела" in stale.answer.call_args.args[0]
    assert unit.id not in configure.module._resources.units


async def test_forms_in_lists_gallery_and_premium_html(app):
    await setup(app)
    item = Module("Forms")
    await app.load(item)
    app.premium = True
    form = await item.form(99, "{e:check} <b>Форма</b>", [[Button("OK", AsyncMock(), style="success", icon="check")]],
                           banner="https://example.org/banner.png")
    stranger = SimpleNamespace(query=f"elys:{form.id}", from_user=SimpleNamespace(id=2), answer=AsyncMock())
    with pytest.raises(StopPropagation):
        await app.inline._query(app.bot, stranger)
    assert stranger.answer.call_args.args[0] == []
    result = (await app.client.get_inline_bot_results("bot", f"elys:{form.id}")).results[0]
    parsed = await Parser(None).parse(result.input_message_content.message_text, mode=ParseMode.HTML)
    assert any(isinstance(e, MessageEntityCustomEmoji) for e in parsed["entities"])
    assert result.input_message_content.link_preview_options.show_above_text
    assert not result.reply_markup.inline_keyboard[0][0].icon_custom_emoji_id
    listing = await item.list(99, ["<b>Первая</b>", "Вторая"])
    await click(app, listing, "Дальше ›")
    assert "Вторая" in listing.data["text"]
    await click(app, listing, "‹ Назад")
    assert "Первая" in listing.data["text"]
    gallery = await item.gallery(99, [Photo("https://example.org/1.jpg", "один"),
                                     Photo("https://example.org/2.jpg", "два")])
    query = await click(app, gallery, "Дальше ›")
    assert query.edit_message_media.call_args.args[0].media.endswith("2.jpg")
    assert gallery.data["index"] == 1
    closed = await click(app, gallery, "Закрыть")
    closed.edit_message_caption.assert_awaited_once()
    assert gallery.id not in app.inline.units.items
    await app.unload("Forms")
    assert not app.inline.units.items
    assert not item._resources.units


async def test_inline_service_handler_and_cleaner_lifecycle(app):
    await setup(app)
    before = dict(app.bot.dispatcher.groups)
    await app.inline.start()
    task = app.inline._cleaner
    assert -1000 in app.bot.dispatcher.groups
    await app.inline.close()
    assert task.cancelled()
    assert dict(app.bot.dispatcher.groups) == before


async def test_input_secret_via_inline_query(app):
    await setup(app)
    item = Module("Private", config=Config(token=Config.secret("old")))
    await app.load(item)
    await invoke(app, ".config Private")
    unit = last_unit(app)
    await click(app, unit, "token")
    q_result = SimpleNamespace(
        query=f"cfg:{unit.id}:set:Private:token <new-secret>",
        from_user=app.client.me,
        inline_message_id="msg-secret",
    )
    with pytest.raises(StopPropagation):
        await app.inline._chosen(app.bot, q_result)
    assert item.config["token"] == "<new-secret>"
    assert "new-secret" not in unit.data["text"]


async def test_core_input_via_inline_query_and_navigation(app):
    await setup(app)
    await invoke(app, ".config")
    unit = last_unit(app)
    await click(app, unit, "Настройки Elys")
    await click(app, unit, "Начало команды")
    q_result = SimpleNamespace(
        query=f"cfg:{unit.id}:core:prefixes ! .",
        from_user=app.client.me,
        inline_message_id="msg-core",
    )
    with pytest.raises(StopPropagation):
        await app.inline._chosen(app.bot, q_result)
    assert app.router.prefixes == ("!", ".")
    assert app.kv.ns("core")["prefixes"] == ["!", "."]
    assert "Сейчас: <code>! .</code>" in unit.data["text"]
    await click(app, unit, "‹ Назад")
    await click(app, unit, "‹ Назад")
    assert "!config" in unit.data["text"]


async def test_config_pages_and_unload_cleans_units(app):
    await setup(app)
    for i in range(10):
        await app.load(Module(f"M{i}", config=Config(value=Config.value(i))))
    await invoke(app, ".config")
    unit = last_unit(app)
    await click(app, unit, "Настройки модулей")
    first = [b.text for b in unit.buttons.values()]
    await click(app, unit, "Следующие ›")
    assert [b.text for b in unit.buttons.values()] != first
    await click(app, unit, "‹ Предыдущие")
    assert [b.text for b in unit.buttons.values()] == first
    await click(app, unit, "M0")
    await click(app, unit, "value")
    await app.unload("Configure")
    assert not app.inline.units.items


@pytest.mark.parametrize("rows", [[], [[]]])
async def test_bot_form_without_buttons_omits_reply_markup(app, rows):
    await setup(app)
    unit = await app.inline.bot_form(configure.module, -10077, "Текст без кнопок", rows)
    assert app.bot.send_message.call_args.kwargs["reply_markup"] is None
    assert unit.data["markup"] is None
    assert not unit.buttons
    unit = await app.inline.bot_form(configure.module, -10077, "С кнопкой", [[Button("OK", AsyncMock())]])
    query = query_for(unit, "OK")
    await app.inline.edit(query, "Кнопки убраны", rows)
    assert query.edit_message_text.call_args.kwargs["reply_markup"] is None
    assert unit.data["markup"] is None
    assert not unit.buttons


@pytest.mark.parametrize("extra_commands", [0, 30])
async def test_welcome_commands_single_page_and_navigation(app, extra_commands):
    from elys.builtin import welcome

    await setup(app)
    await app.load(welcome.module)
    item = Module("Extra")
    for index in range(extra_commands):
        item.command(f"extra{index}")(AsyncMock())
    await app.load(item)
    query = SimpleNamespace(message=SimpleNamespace(chat=SimpleNamespace(id=-10077)), answer=AsyncMock())
    await welcome.commands(app.bot, query)
    unit = last_unit(app)
    query.answer.assert_awaited_once()
    assert ".ping" in unit.data["text"]
    assert ".help Ping" in unit.data["text"]
    sent = app.bot.send_message.call_args
    assert sent.args[0] == -10077
    if extra_commands:
        markup = sent.kwargs["reply_markup"]
        raw_markup = await markup.write(app.bot)
        assert raw_markup.rows and all(row.buttons for row in raw_markup.rows)
        assert list(button.text for button in unit.buttons.values()) == ["Дальше ›"]
        await click(app, unit, "Дальше ›")
        assert ".extra29" in unit.data["text"]
        assert list(button.text for button in unit.buttons.values()) == ["‹ Назад"]
        await click(app, unit, "‹ Назад")
        assert ".ping" in unit.data["text"]
    else:
        assert sent.kwargs["reply_markup"] is None
        assert not unit.buttons


async def test_failed_form_creation_and_failed_edits_do_not_leak_or_replace_buttons(app):
    await setup(app)
    owner = configure.module
    with pytest.raises(ValueError):
        await owner.form(99, "text", [[Button("invalid")]])
    assert not app.inline.units.items and not owner._resources.units
    with pytest.raises(ValueError):
        await app.inline.bot_form(owner, 1, "text", [[Button("invalid")]])
    assert not app.inline.units.items and not owner._resources.units
    app.client.send_inline_bot_result.side_effect = RuntimeError("network")
    with pytest.raises(RuntimeError):
        await owner.form(99, "text")
    assert not app.inline.units.items and not owner._resources.units
    app.client.send_inline_bot_result.side_effect = None
    unit = await owner.form(99, "text", [[Button("ok", AsyncMock())]])
    previous = dict(unit.buttons)
    query = query_for(unit, "ok")
    query.edit_message_text.side_effect = RuntimeError("network")
    with pytest.raises(RuntimeError):
        await app.inline.edit(query, "new", [[Button("new", AsyncMock())]])
    assert unit.buttons == previous
    assert unit.data["text"] == "text"
