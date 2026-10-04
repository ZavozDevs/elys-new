import asyncio

import pytest

from elys.builtin.eval import _traceback, run


async def test_last_expression_is_result():
    assert await run("x = 2\nx * 3", {}) == 6


async def test_top_level_await():
    assert await run("await asyncio.sleep(0, 'ok')", {"asyncio": asyncio}) == "ok"


async def test_statement_has_no_result():
    env = {}
    assert await run("y = 1", env) is None
    assert env["y"] == 1


async def test_traceback_starts_at_user_code():
    with pytest.raises(ZeroDivisionError) as info:
        await run("a = 1\n1 / 0", {})
    text = _traceback(info.value)
    assert 'File "<eval>", line 2' in text
    assert "1 / 0" in text
    assert "elys/builtin" not in text


@pytest.mark.parametrize("text", ["😀" * 3000, "<>&" * 1500, "a😀b" * 1500])
async def test_truncation_counts_parsed_text_not_html_markup(text):
    import html

    from pyrogram.parser.html import HTML

    from elys.builtin.eval import _truncate

    shortened = _truncate(text, 4000)
    parsed = await HTML(None).parse(f"<pre>{html.escape(shortened)}</pre>")
    assert parsed["message"] == shortened
    assert len(parsed["message"].encode("utf-16-le")) // 2 <= 4000
    assert shortened.endswith("…")
    assert "\ufffd" not in shortened


def test_html_escaping_does_not_reduce_available_space():
    from elys.builtin.eval import _truncate

    assert _truncate("<" * 3000, 4000) == "<" * 3000
