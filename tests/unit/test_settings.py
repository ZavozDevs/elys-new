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
