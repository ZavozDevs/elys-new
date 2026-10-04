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


def test_integer_number_and_series_validation():
    cfg = Config(
        limit=Config.integer(5, min=1, max=10),
        ratio=Config.number(1.5, min=0.0, max=5.0),
        tags=Config.series(["alpha", "beta"], item_type=str),
    )
    assert cfg["limit"] == 5
    assert cfg["ratio"] == 1.5
    assert cfg["tags"] == ["alpha", "beta"]

    cfg["limit"] = 10
    cfg["ratio"] = 0.0
    cfg["tags"] = ["gamma"]
    assert cfg["limit"] == 10
    assert cfg["ratio"] == 0.0
    assert cfg["tags"] == ["gamma"]

    for bad_limit in (0, 11, "5", 5.5):
        with pytest.raises(ValueError):
            cfg["limit"] = bad_limit

    for bad_ratio in (-0.1, 5.1, "1.5"):
        with pytest.raises(ValueError):
            cfg["ratio"] = bad_ratio

    for bad_tags in ([1, 2], "not-a-list", [None]):
        with pytest.raises(ValueError):
            cfg["tags"] = bad_tags
