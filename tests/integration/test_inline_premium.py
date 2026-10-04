import contextlib
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram import StopPropagation
from pyrogram.errors import FloodWait, MessageNotModified

import elys.inline.form as form_module
from elys import Button, Module, Photo
from tests.integration.test_loader import app as app
from tests.integration.test_stage2_commands import setup

TEXT = "{e:check} <b>Форма</b>"
TOKEN = "123456:" + "x" * 35


async def prepare(app, *, premium=True, feedback=True, chosen=True):
    await setup(app)
    item = Module("Forms")
    await app.load(item)
    app.premium = premium
    core = app.kv.ns("core")
    core["bot_token"] = TOKEN
    if feedback:
        core["bot_feedback"] = TOKEN
    app.bot.edit_inline_text = AsyncMock()
    app.bot.edit_inline_caption = AsyncMock()
    events = []

    async def sent(chat_id, query_id, result_id, **kwargs):
        events.append("sent")
        if chosen:
            result = SimpleNamespace(result_id=result_id, inline_message_id="imid")
            with contextlib.suppress(StopPropagation):
                await app.inline._chosen(app.bot, result)

    app.client.send_inline_bot_result = AsyncMock(side_effect=sent)
    app.bot.edit_inline_text.side_effect = lambda *a, **k: events.append("edit")
    return item, events


async def first_result(app, unit):
    return (await app.client.get_inline_bot_results("bot", f"elys:{unit.id}")).results[0]


async def test_premium_form_is_sent_as_star_then_edited_with_full_text_and_buttons(app):
    item, events = await prepare(app)
    seen = []
    original = app.client.get_inline_bot_results

    async def get_results(bot, text):
        results = await original(bot, text)
        seen.append(results.results[0].input_message_content.message_text)
        return results

    app.client.get_inline_bot_results = get_results
    unit = await item.form(99, TEXT, [[Button("OK", AsyncMock())]], banner="https://example.org/b.png")
    assert seen == ["⭐"]  # Telegram вырезает премиум-эмодзи из inline-результата
    assert events == ["sent", "edit"]
    app.bot.edit_inline_text.assert_awaited_once()
    args, kwargs = app.bot.edit_inline_text.call_args
    assert args[0] == "imid" and '<tg-emoji emoji-id="' in args[1] and "<b>Форма</b>" in args[1]
    assert kwargs["reply_markup"] is unit.data["markup"] and kwargs["link_preview_options"].show_above_text
    assert "sent" not in unit.data
    # Повторный запрос после правки отдаёт полный текст, а не заглушку.
    assert "tg-emoji" in (await first_result(app, unit)).input_message_content.message_text


async def test_edit_does_not_wait_a_fixed_delay(app, monkeypatch):
    item, _ = await prepare(app)
    sleeps = []
    monkeypatch.setattr(form_module.asyncio, "sleep", AsyncMock(side_effect=lambda t: sleeps.append(t)))
    await item.form(99, TEXT, [[Button("OK", AsyncMock())]])
    assert [t for t in sleeps if t != 60] == []  # 60 с — фоновая очистка форм, не правка


@pytest.mark.parametrize("premium, feedback", [(False, True), (True, False)])
async def test_no_placeholder_without_premium_or_feedback(app, premium, feedback):
    item, events = await prepare(app, premium=premium, feedback=feedback)
    unit = await item.form(99, TEXT, [[Button("OK", AsyncMock())]])
    text = (await first_result(app, unit)).input_message_content.message_text
    assert "⭐" not in text and "Форма" in text
    assert events == ["sent"]
    app.bot.edit_inline_text.assert_not_awaited()
    assert "sent" not in unit.data


async def test_plain_text_form_is_not_deferred_for_premium(app):
    item, events = await prepare(app)
    unit = await item.form(99, "<b>Без эмодзи</b>", [[Button("OK", AsyncMock())]])
    assert events == ["sent"] and "sent" not in unit.data
    app.bot.edit_inline_text.assert_not_awaited()


async def test_stale_feedback_flag_for_other_token_is_ignored(app):
    item, events = await prepare(app)
    app.kv.ns("core")["bot_feedback"] = "654321:" + "y" * 35
    await item.form(99, TEXT, [[Button("OK", AsyncMock())]])
    assert events == ["sent"]


async def test_missing_chosen_update_warns_and_keeps_form(app, monkeypatch, caplog):
    item, _ = await prepare(app, chosen=False)
    original = form_module.asyncio.wait_for
    monkeypatch.setattr(form_module.asyncio, "wait_for", lambda future, timeout: original(future, 0.05))
    with caplog.at_level(logging.WARNING):
        unit = await item.form(99, TEXT, [[Button("OK", AsyncMock())]])
    assert "Inline Feedback" in caplog.text
    app.bot.edit_inline_text.assert_not_awaited()
    assert unit.id in app.inline.units.items and "sent" not in unit.data


async def test_edit_retries_then_gives_up_without_losing_the_form(app, monkeypatch, caplog):
    item, _ = await prepare(app)
    monkeypatch.setattr(form_module.asyncio, "sleep", AsyncMock())
    app.bot.edit_inline_text.side_effect = [FloodWait(value=1), FloodWait(value=1), None]
    unit = await item.form(99, TEXT, [[Button("OK", AsyncMock())]])
    assert app.bot.edit_inline_text.await_count == 3 and unit.id in app.inline.units.items
    app.bot.edit_inline_text.reset_mock(side_effect=True)
    app.bot.edit_inline_text.side_effect = FloodWait(value=1)
    with caplog.at_level(logging.ERROR):
        unit = await item.form(99, TEXT, [[Button("OK", AsyncMock())]])
    assert app.bot.edit_inline_text.await_count == 4 and unit.id in app.inline.units.items
    assert "премиум-эмодзи" in caplog.text
    app.bot.edit_inline_text.reset_mock(side_effect=True)
    app.bot.edit_inline_text.side_effect = MessageNotModified
    await item.form(99, TEXT, [[Button("OK", AsyncMock())]])
    assert app.bot.edit_inline_text.await_count == 1


async def test_premium_gallery_caption_and_list_use_the_same_flow(app):
    item, _ = await prepare(app)
    gallery = await item.gallery(99, [Photo("https://example.org/1.jpg", "{e:check} один"),
                                      Photo("https://example.org/2.jpg", "два")])
    app.bot.edit_inline_caption.assert_awaited_once()
    args, kwargs = app.bot.edit_inline_caption.call_args
    assert args[0] == "imid" and "tg-emoji" in args[1] and kwargs["reply_markup"] is gallery.data["markup"]
    app.bot.edit_inline_text.assert_not_awaited()
    listing = await item.list(99, ["{e:check} Первая", "Вторая"])
    app.bot.edit_inline_text.assert_awaited_once()
    assert "tg-emoji" in app.bot.edit_inline_text.call_args.args[1] and listing.id in app.inline.units.items


async def test_chosen_for_unknown_form_is_harmless_and_failed_send_removes_the_form(app):
    item, _ = await prepare(app)
    with pytest.raises(StopPropagation):
        await app.inline._chosen(app.bot, SimpleNamespace(result_id="gone", inline_message_id="x"))
    app.client.send_inline_bot_result.side_effect = RuntimeError("send failed")
    with pytest.raises(RuntimeError):
        await item.form(99, TEXT, [[Button("OK", AsyncMock())]])
    assert not app.inline.units.items


async def test_inline_form_buttons_use_plain_emoji_but_bot_messages_keep_premium_icons(app):
    from tests.inline_helpers import query_for

    item, _ = await prepare(app)
    unit = await item.form(99, "<b>Форма</b>", [[Button("Настройки", AsyncMock(), icon="gear")]])
    button = (await first_result(app, unit)).reply_markup.inline_keyboard[0][0]
    # Telegram вырезает иконку у inline-сообщений: вместо неё обычный эмодзи в тексте.
    assert button.text == "⚙️ Настройки" and not button.icon_custom_emoji_id

    direct = await app.inline.bot_form(item, 99, "<b>Форма</b>", [[Button("Настройки", AsyncMock(), icon="gear")]])
    sent = app.bot.send_message.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert sent.text == "Настройки" and sent.icon_custom_emoji_id
    # После нажатия кнопки правка того же сообщения не теряет иконку.
    query = query_for(direct, "Настройки")
    await app.inline.edit(query, "<b>Экран 2</b>", [[Button("Закрыть", AsyncMock(), icon="cross")]])
    edited = query.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert edited.text == "Закрыть" and edited.icon_custom_emoji_id

    app.premium = False  # без Premium у владельца иконка невозможна и в сообщении бота
    plain = await app.inline.bot_form(item, 99, "x", [[Button("Настройки", AsyncMock(), icon="gear")]])
    assert plain.data["markup"].inline_keyboard[0][0].text == "⚙️ Настройки"
