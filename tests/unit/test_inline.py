import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram.enums import ButtonStyle, ParseMode
from pyrogram.parser import Parser

from elys import Button, Config, Module, Photo
from elys.builtin.configure import parse_value, shown
from elys.inline.units import Units
from elys.log import TelegramLogHandler
from tests.unit.test_log import record


def owner():
    module = Module("Test")
    module.loaded = True
    return module


def test_units_ttl_owner_resources_collision_and_unload(monkeypatch):
    units, module = Units(clock=lambda: 100), owner()
    first = units.add(module, "form", {}, {1}, ttl=2)
    assert len(first.id) == 8 and first.id.isalnum()
    assert first.allowed_ids == {1}
    assert first.id in module._resources.units
    assert units.get(first.id) is first
    units.clock = lambda: 102
    units.sweep()
    assert not units.items and not module._resources.units
    second = units.add(module, "list", {}, {1})
    module.loaded = False
    assert units.get(second.id) is None
    module.loaded = True
    units.add(module, "gallery", {}, {1})
    other = owner()
    remaining = units.add(other, "form", {}, {2})
    units.remove_owner(module)
    assert list(units.items) == [remaining.id]
    units.clear()
    assert not other._resources.units
    with pytest.raises(ValueError):
        units.add(module, "form", {}, {1}, ttl=0)


@pytest.mark.parametrize("direct,premium,style,visible", [
    (True, True, "success", True), (True, True, "default", True),  # бот отправил сам, владелец с Premium
    (False, True, "primary", False), (True, False, "danger", False),
])
def test_button_icons_follow_telegram_constraints(direct, premium, style, visible):
    button = Button("Готово", AsyncMock(), icon="check", style=style)
    result = button.render("Abc12345:0", direct=direct, premium=premium)
    assert bool(result.icon_custom_emoji_id) is visible
    # Где премиум-иконка невозможна, вместо неё обычный эмодзи перед текстом.
    assert result.text == ("Готово" if visible else "✅ Готово")
    assert result.style == ButtonStyle[style.upper()]
    assert len(result.callback_data.encode()) <= 64


def test_button_without_icon_is_unchanged():
    result = Button("Готово", AsyncMock()).render("Abc12345:0", direct=True, premium=True)
    assert result.text == "Готово" and not result.icon_custom_emoji_id


def test_button_requires_one_action_and_photo_public_url():
    with pytest.raises(ValueError):
        Button("bad").render()
    with pytest.raises(ValueError):
        Button("bad", AsyncMock(), url="https://example.org").render()
    with pytest.raises(ValueError):
        Button("bad", AsyncMock(), query="cfg ").render()
    with pytest.raises(ValueError):
        Button("bad", url="https://example.org", query="cfg ").render()
    assert Button("Открыть", url="https://example.org").render().callback_data is None
    btn_query = Button("Инлайн", query="cfg:{unit_id}:set:Mod:key ").render("Unit1234:0")
    assert btn_query.switch_inline_query_current_chat == "cfg:Unit1234:set:Mod:key "
    assert btn_query.callback_data is None
    with pytest.raises(ValueError):
        Photo("file:///tmp/private.jpg")


@pytest.mark.parametrize("field,text,expected", [
    (Config.value(1), "-2", -2), (Config.value(1.0), "1,5", 1.5),
    (Config.value([]), '["a", 2]', ["a", 2]), (Config.value({}), '{"a": 1}', {"a": 1}),
    (Config.value(None), 'null', None), (Config.secret(), "<secret>", "<secret>"),
    (Config.url(), "https://example.org/x", "https://example.org/x"),
])
def test_config_input_types(field, text, expected):
    assert parse_value(field, text) == expected


@pytest.mark.parametrize("field,text", [
    (Config.value(1), "1.2"), (Config.value(1.0), "nan"), (Config.value([]), '{}'),
    (Config.url(), "https://user:pass@example.org"), (Config.choice("a", ["a", "b"]), "c"),
])
def test_config_rejects_invalid_values(field, text):
    with pytest.raises((ValueError, TypeError)):
        parse_value(field, text)


async def test_secret_display_and_html_escaping():
    assert "secret" not in shown("secret", secret=True)
    assert "&lt;" in shown("<value>")
    parsed = await Parser(None).parse(shown("<value>"), mode=ParseMode.HTML)
    assert parsed["message"] == "<value>"


async def test_telegram_log_batches_retries_and_avoids_recursion():
    handler = TelegramLogHandler()
    for i in range(7):
        handler.handle(record(level=40, msg="<error>" * 100, error_id=str(i)))
    handler.handle(record(level=40, msg="delivery failed", no_telegram=True))
    assert len(handler.pending) == 14  # полный текст: два фрагмента каждой ошибки
    sink = AsyncMock(side_effect=RuntimeError("offline"))
    handler.sink = sink
    await handler.flush_pending()
    assert len(handler.pending) == 14
    handler.sink = AsyncMock(return_value=SimpleNamespace(id=1))
    await handler.flush_pending()
    assert not handler.pending
    assert handler.sink.await_count > 1
    for call in handler.sink.call_args_list:
        assert len(call.args[0]) < 4096
        assert "&lt;error&gt;" in call.args[0]
        await Parser(None).parse(call.args[0], mode=ParseMode.HTML)
    handler.attach(handler.sink)
    task = handler.task
    await asyncio.sleep(0)
    await handler.stop()
    assert task.cancelled()
