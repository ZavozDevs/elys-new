from html import unescape

import pytest
from pyrogram.enums import ParseMode
from pyrogram.parser import Parser
from pyrogram.raw.types import MessageEntityBlockquote, MessageEntityCode, MessageEntityCustomEmoji

from elys import Module
from elys.builtin.configure import apply_core
from tests.inline_helpers import last_unit
from tests.integration.test_loader import app as app
from tests.integration.test_loader import source as source
from tests.integration.test_stage2_commands import invoke, setup


async def parse(text):
    return await Parser(None).parse(text, mode=ParseMode.HTML)


@pytest.mark.parametrize("premium", [False, True])
async def test_builtin_screens_use_real_telegram_quotes_and_code(app, premium):
    await setup(app)
    app.premium = premium
    for command in (".help", ".help Ping", ".lm", ".dlm", ".ping", ".config"):
        message = await invoke(app, command)
        if command == ".config":
            # Команда удаляется, а экран — это текст формы в чате.
            assert message.deleted and not message.edits
            text = app.inline._text(last_unit(app).data["text"])
        else:
            assert not message.deleted
            text = message.edits[-1]
        parsed = await parse(text)
        assert any(isinstance(e, MessageEntityBlockquote) for e in parsed["entities"]), command
        assert any(isinstance(e, MessageEntityCode) for e in parsed["entities"]), command
        assert "<blockquote" not in parsed["message"]
        assert "<code>" not in parsed["message"]
        assert "{e:" not in parsed["message"]
        if command != ".ping":
            assert any(isinstance(e, MessageEntityCustomEmoji) for e in parsed["entities"]) is premium
    # Справка не превращается в инструкцию по установке и план разработки.
    overview = (await parse((await invoke(app, ".help")).edits[0]))["message"]
    assert len(overview) < 550
    assert ".dlm" in overview and ".config" in overview and ".help Ping" in overview
    detail = (await invoke(app, ".help Ping")).edits[0]
    assert "этап" not in detail and ".config" not in detail


async def test_layout_escapes_dynamic_content_and_uses_current_prefix(app):
    await setup(app)
    item = Module("<Demo&>", version="<2>", author="<Author&>")

    @item.command("demo", aliases=("d",))
    async def demo(client, message):
        """<текст> — пример с <b>разметкой</b> & символами."""

    # Предупреждение относится к вотчерам без явно заданной области работы.
    @item.on_message()
    async def watch(client, message):
        pass

    await app.load(item)
    apply_core(app, "prefixes", "<&")
    for command in ("help", "help <Demo&>", "lm", "dlm"):
        response = (await invoke(app, "<&" + command)).edits[0]
        assert "<Demo&>" not in response and "<Author&>" not in response
        parsed = await parse(response)
        assert "<&" in parsed["message"]
        assert ".help" not in parsed["message"]
    detail = (await invoke(app, "<&help <Demo&>")).edits[0]
    parsed = await parse(detail)
    assert "<Author&>" in parsed["message"] and "<2>" in parsed["message"]
    assert "<b>разметкой</b> & символами" in parsed["message"]
    assert "слушает все сообщения" in parsed["message"].lower()
    assert "[…]" in parsed["message"]
    assert "<&d" in parsed["message"]


@pytest.mark.parametrize("language", ["ru", "en"])
async def test_disabled_module_has_executable_restore_hint(app, source, language):
    await setup(app)
    app.language = language
    loaded = await invoke(app, f".dlm {source} --trust")
    assert "<blockquote>" in loaded.edits[-1]
    apply_core(app, "prefixes", "!")
    response = await invoke(app, "!ulm Hello")
    assert "<code>!lm hello</code>" in response.edits[-1]
    assert "<code>!lm Hello</code>" not in response.edits[-1]
    listing = (await invoke(app, "!lm")).edits[0]
    assert "Выключены · 1" in listing
    assert "<code>!lm hello</code>" in listing
    await invoke(app, "!lm hello")
    assert "Hello" in app.modules
    response = await invoke(app, "!ulm Hello --purge --yes")
    assert "безвозвратно" in response.edits[-1]
    assert "Файл оставлен" in response.edits[-1]
    assert "<code>!lm hello</code>" in response.edits[-1]


async def test_install_notice_is_short_but_keeps_security_boundary(app):
    await setup(app)
    text = (await invoke(app, ".dlm")).edits[0]
    plain = (await parse(text))["message"]
    assert len(plain) < 420
    assert "зависимости" in plain
    assert "полный доступ к аккаунту и компьютеру" in plain
    assert "не проверка безопасности" in plain
    assert ".dlm <ссылка или путь> --trust" in unescape(text)
    assert "<code>.dlm --trust</code>" in text
