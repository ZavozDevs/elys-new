from unittest.mock import AsyncMock

import pytest
from pyrogram import enums, errors
from pyrogram.types import User

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
    out = capsys.readouterr().out
    assert out.count("✗") == 2
    assert "нужны только цифры" in out and "нужно 32 символа" in out


@pytest.mark.parametrize("stage", ["send_phone_number_code", "sign_in", "check_password"])
async def test_flood_wait_is_shown_before_sleep_and_request_retried(stage, monkeypatch):
    from types import SimpleNamespace

    user = User(id=1, first_name="Test")
    sent = SimpleNamespace(type=enums.SentCodeType.APP, phone_code_hash="hash")
    client = SimpleNamespace(
        send_phone_number_code=AsyncMock(return_value=sent),
        sign_in=AsyncMock(return_value=user),
        check_password=AsyncMock(return_value=user),
        get_password_hint=AsyncMock(return_value=None),
    )
    method = getattr(client, stage)
    method.side_effect = [errors.FloodWait(3), sent if stage == "send_phone_number_code" else user]
    shown = []
    monkeypatch.setattr(wizard.term, "hint", shown.append)
    monkeypatch.setattr(wizard.term, "aask", AsyncMock(side_effect=["+79991234567", "12345", "password"]))

    async def sleep(seconds):
        assert seconds == 3
        assert "3 с" in shown[-1]  # не после ожидания

    monkeypatch.setattr(wizard.asyncio, "sleep", sleep)
    result = await (wizard._password(client) if stage == "check_password" else wizard._phone(client))
    assert result is user
    assert method.await_count == 2
    assert method.await_args_list[0] == method.await_args_list[1]
