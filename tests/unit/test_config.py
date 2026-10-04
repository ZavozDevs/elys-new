import pytest

from elys import Config
from elys.storage.kv import KV


def test_validation_and_secret_repr():
    config = Config(key=Config.secret("private-value"), count=Config.value(1),
                    units=Config.choice("metric", ["metric", "imperial"]), banner=Config.url())
    assert "private-value" not in repr(config)
    assert "private-value" not in repr(config.fields["key"])
    for key, value in (("count", True), ("count", "1"), ("units", "wrong"),
                       ("banner", "file:///tmp/a"), ("banner", "https://user:pass@example.org/a")):
        with pytest.raises(ValueError):
            config[key] = value
    assert config["count"] == 1
    config["banner"] = "https://example.org/image.png"
    del config["banner"]
    assert config["banner"] == ""
    with pytest.raises(ValueError):
        Config.choice("x", [])
    with pytest.raises(TypeError):
        Config(items=Config.value((1, 2)))


def test_mutable_values_are_copied():
    original = [1]
    config = Config(items=Config.value(original))
    config["items"].append(2)
    assert config["items"] == [1]
    config["items"] = [1, 3]
    assert original == [1]
    assert config["items"] == [1, 3]


async def test_config_persists_and_bad_saved_values_are_not_replaced(tmp_path):
    path = tmp_path / "db"
    kv = await KV.open(path)
    config = Config(count=Config.value(1))
    config.bind(kv.ns("cfg:Test"))
    config["count"] = 2
    await kv.close()
    kv = await KV.open(path)
    try:
        restored = Config(count=Config.value(1))
        restored.bind(kv.ns("cfg:Test"))
        assert restored["count"] == 2
        kv.ns("cfg:Test")["count"] = "bad"
        with pytest.raises(ValueError):
            Config(count=Config.value(1)).bind(kv.ns("cfg:Test"))
        assert kv.ns("cfg:Test")["count"] == "bad"
    finally:
        await kv.close()
