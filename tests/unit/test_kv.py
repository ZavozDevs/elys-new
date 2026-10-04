import asyncio

import pytest

from elys.storage.kv import KV


@pytest.fixture
def path(tmp_path):
    return tmp_path / "elys.db"


async def reopen(kv, path):
    await kv.close()
    return await KV.open(path)


async def test_roundtrip_and_namespaces(path):
    kv = await KV.open(path, delay=60)
    a, b = kv.ns("a"), kv.ns("b")
    a["x"] = {"n": 1, "s": "привет"}
    b["x"] = [1, 2]
    assert kv.ns("a") is a
    kv = await reopen(kv, path)  # close сбрасывает отложенную запись
    assert kv.ns("a")["x"] == {"n": 1, "s": "привет"}
    assert kv.ns("b")["x"] == [1, 2]
    await kv.close()


async def test_write_behind_batches(path):
    kv = await KV.open(path, delay=0.02)
    db = kv.ns("m")
    db["a"] = 1
    db["b"] = 2
    probe = await KV.open(path)
    assert "a" not in probe.ns("m")  # ещё в памяти
    await probe.close()
    await asyncio.sleep(0.1)
    probe = await KV.open(path)
    assert dict(probe.ns("m")) == {"a": 1, "b": 2}
    await probe.close()
    await kv.close()


async def test_delete_and_touch(path):
    kv = await KV.open(path, delay=60)
    db = kv.ns("m")
    db["gone"] = 1
    db["list"] = [1]
    await db.flush()
    del db["gone"]
    db["list"].append(2)
    db.touch("list")
    with pytest.raises(KeyError):
        db.touch("missing")
    kv = await reopen(kv, path)
    assert dict(kv.ns("m")) == {"list": [1, 2]}
    await kv.close()


@pytest.mark.parametrize("value", [object(), {1, 2}, (1, 2), {1: "x"}, float("nan"), float("inf"), {"x": [object()]}])
async def test_bad_value_does_not_block_others(path, value):
    kv = await KV.open(path, delay=60)
    db = kv.ns("m")
    with pytest.raises((TypeError, ValueError)):
        db["bad"] = value
    assert "bad" not in db
    db["ok"] = 1
    kv = await reopen(kv, path)
    assert dict(kv.ns("m")) == {"ok": 1}
    await kv.close()


async def test_mapping_api(path):
    kv = await KV.open(path, delay=60)
    db = kv.ns("m")
    assert db.setdefault("n", 0) == 0
    db.set("n", db["n"] + 1)
    assert db.get("n") == 1
    assert db.get("missing", "d") == "d"
    assert list(db) == ["n"]
    assert len(db) == 1
    await kv.close()


async def test_invalid_overwrite_preserves_old_value_and_rejects_cycles(path):
    kv = await KV.open(path, delay=60)
    db = kv.ns("m")
    db["x"] = 7
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="циклическое"):
        db["x"] = cycle
    assert db["x"] == 7
    with pytest.raises(TypeError, match="ключ"):
        db[1] = "bad"
    await kv.close()


async def test_flush_failure_retains_batch_for_retry(path):
    kv = await KV.open(path, delay=60)
    db = kv.ns("m")
    db["x"] = []
    db["ok"] = 1
    db["x"].append(object())
    with pytest.raises(TypeError):
        db.touch("x")
    with pytest.raises(TypeError):
        await db.flush()
    db["x"].clear()
    db.touch("x")
    await db.flush()
    kv = await reopen(kv, path)
    assert dict(kv.ns("m")) == {"x": [], "ok": 1}
    await kv.close()


async def test_close_joins_timer_and_rejects_writes(path):
    kv = await KV.open(path, delay=60)
    db = kv.ns("m")
    db["x"] = 1
    timer = kv._timer
    await kv.close()
    assert timer.done()
    for operation in (lambda: db.set("x", 2), lambda: db.pop("x"), lambda: db.touch("x")):
        with pytest.raises(RuntimeError, match="закрыт"):
            operation()
    assert db["x"] == 1
    await kv.close()
