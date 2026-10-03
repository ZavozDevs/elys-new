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
