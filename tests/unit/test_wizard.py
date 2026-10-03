import pytest

from elys import wizard
from elys.settings import load

HASH = "0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(("text", "value"), [(" 123 ", 123), ("0", None), ("12a", None), ("", None)])
def test_parse_api_id(text, value):
    assert wizard.parse_api_id(text) == value


@pytest.mark.parametrize(("text", "value"), [(HASH.upper(), HASH), ("abc", None), (HASH + "0", None)])
def test_parse_api_hash(text, value):
    assert wizard.parse_api_hash(text) == value


def test_save_and_forget_keep_other_settings(tmp_path):
    file = tmp_path / "data" / "settings.toml"
    file.parent.mkdir()
    file.write_text('api_id = 1\nprefixes = ["!"]\n')
    wizard.save_keys(file, 42, HASH)
    s = load({"ELYS_DATA_DIR": str(file.parent)})
    assert (s.api_id, s.api_hash, s.prefixes) == (42, HASH, ("!",))
    wizard.forget_keys(file)
    assert file.read_text() == 'prefixes = ["!"]\n'


def test_ask_keys_reasks_until_valid(tmp_path, monkeypatch, capsys):
    answers = iter(["abc", "777", "nope", HASH])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    file = tmp_path / "settings.toml"
    wizard.ask_keys(file)
    assert load({"ELYS_DATA_DIR": str(tmp_path)}).api_id == 777
    assert capsys.readouterr().out.count("не похоже") == 2
