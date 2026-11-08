from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pyrogram.parser import Parser

from elys import E, builtin, html
from elys.i18n import catalog
from elys.sdk.context import current
from elys.ui.emoji import REGISTRY, render, unknown


def test_registry_and_every_builtin_template():
    for name, (identity, fallback) in REGISTRY.items():
        assert identity.isdecimal() and fallback, name
    strings = []
    for path in Path("elys/i18n/langs").glob("*/*.yml"):
        if path.stem != "_meta":
            strings.extend(yaml.safe_load(path.read_text()).values())
    for name in builtin.NAMES:
        module = import_module(f"elys.builtin.{name}").module
        for locale in module.strings.values():
            strings.extend(locale.values())
    for text in strings:
        assert not unknown(text), text


def test_ping_templates_use_only_known_emoji():
    from elys.i18n import BUILTIN

    for pack in BUILTIN.glob("*/ping.yml"):
        assert not unknown(yaml.safe_load(pack.read_text("utf-8"))["template"]), pack


@pytest.mark.parametrize("premium", [False, True])
async def test_emoji_in_html_is_parsed_by_real_wzgram(premium):
    host = SimpleNamespace(premium=premium)
    token = current.set(host)
    try:
        text = html.b("<test>") + " " + E.check + " " + html.emoji("123", "🌧")
        parsed = await Parser(None).parse(text, mode=__import__("pyrogram").enums.ParseMode.HTML)
        assert parsed["message"] == "<test> ✅ 🌧"
        entities = [entity for entity in parsed["entities"]
                    if getattr(entity, "document_id", None) is not None]
        assert len(entities) == (2 if premium else 0)
        host.premium = not premium
        assert ("tg-emoji" in E["check"]) is not premium
    finally:
        current.reset(token)


def test_template_arguments_are_escaped_and_not_rendered():
    strings = {"ru": {"status": "{e:check} {value}"}, "en": {"only": "english"}}
    def translate(_, key, **values):
        return catalog.t(key, sections=(), extra=strings, **values)
    assert translate(strings, "status", value="<b>{e:stop}</b>") == "✅ &lt;b&gt;{e:stop}&lt;/b&gt;"
    assert translate(strings, "only", language="xx") == "english"
    assert translate(strings, "absent") == "absent"
    assert render("{e:does_not_exist}") == "❔"
    assert unknown("{e:does_not_exist}") == {"does_not_exist"}


def test_html_helpers_escape_text_and_attributes():
    assert html.quote("<x>", expandable=True) == "<blockquote expandable>&lt;x&gt;</blockquote>"
    assert html.link("<x>", 'https://example.org/?a="') == '<a href="https://example.org/?a=&quot;">&lt;x&gt;</a>'
    assert html.pre("<code>") == "<pre>&lt;code&gt;</pre>"
    with pytest.raises(ValueError):
        html.link("bad", "javascript:alert(1)")
    with pytest.raises(ValueError):
        html.emoji('1" bad="', "x")
