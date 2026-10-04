import pytest

from elys.settings import MissingKeys, SettingsError, load


def env(tmp_path, **extra):
    return {"ELYS_DATA_DIR": str(tmp_path), **extra}


def test_file_and_env(tmp_path):
    (tmp_path / "settings.toml").write_text(
        'api_id = 1\napi_hash = "h"\nprefixes = ["!"]\n[rate_limits]\nmessage = { rate = 1, burst = 2 }\n'
    )
    s = load(env(tmp_path, ELYS_API_ID="42", ELYS_PREFIXES=". ,"))
    assert s.api_id == 42
    assert s.api_hash == "h"
    assert s.prefixes == (".", ",")
    assert s.rate_limits == {"message": {"rate": 1, "burst": 2}}
    assert s.data_dir == tmp_path
    assert s.file == tmp_path / "settings.toml"


def test_missing_keys_points_to_file(tmp_path):
    with pytest.raises(MissingKeys) as info:
        load(env(tmp_path))
    assert info.value.args[0] == tmp_path / "settings.toml"


@pytest.mark.parametrize(("text", "error"), [('api_id = 1\napi_hash = "h"\ntypo = 1', "typo"), ("api_id = ", "toml")])
def test_errors(tmp_path, text, error):
    (tmp_path / "settings.toml").write_text(text)
    with pytest.raises(SettingsError, match=error):
        load(env(tmp_path))


@pytest.mark.parametrize(
    "extra",
    [
        {"ELYS_LOG_LEVEL": "verbose"},
        {"ELYS_API_ID": ""},
        {"ELYS_API_ID": "0"},
        {"ELYS_API_HASH": " "},
        {"ELYS_PREFIXES": ""},
        {"ELYS_RATE_LIMITS": "bad json"},
        {"ELYS_RATE_LIMITS": '{"message": {"rate": 0}}'},
        {"ELYS_RATE_LIMITS": '{"message": {"rate": true}}'},
        {"ELYS_RATE_LIMITS": '{"message": {"typo": 1}}'},
    ],
)
def test_invalid_env_is_settings_error(tmp_path, extra):
    values = env(tmp_path, ELYS_API_ID="1", ELYS_API_HASH="h")
    values.update(extra)
    with pytest.raises(SettingsError) as info:
        load(values)
    assert not isinstance(info.value, MissingKeys)


def test_rate_limits_json_and_stable_prefixes(tmp_path):
    s = load(env(
        tmp_path, ELYS_API_ID="1", ELYS_API_HASH="h", ELYS_LOG_LEVEL="debug",
        ELYS_PREFIXES="! . ! ..", ELYS_RATE_LIMITS='{"message": {"rate": 2, "burst": 3}}',
    ))
    assert s.prefixes == ("!", ".", "..")
    assert s.log_level == "DEBUG"
    assert s.rate_limits == {"message": {"rate": 2, "burst": 3}}


@pytest.mark.parametrize("value", ["[1]", "[]", "[\"a b\"]", "true"])
def test_invalid_prefixes_in_toml(tmp_path, value):
    (tmp_path / "settings.toml").write_text(f'api_id = 1\napi_hash = "h"\nprefixes = {value}\n')
    with pytest.raises(SettingsError, match="prefixes"):
        load(env(tmp_path))
