import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pyrogram import enums, errors
from pyrogram.types import User

from elys import __main__ as cli
from elys import app, settings, wizard


def test_second_settings_error_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    load = Mock(side_effect=[settings.MissingKeys(tmp_path), settings.SettingsError("bad")])
    monkeypatch.setattr(settings, "load", load)
    monkeypatch.setattr(wizard, "ask_keys", Mock())
    with pytest.raises(SystemExit, match="Ошибка в настройках: bad"):
        cli.main([])


@pytest.mark.parametrize("configured", [False, True])
def test_first_login_with_line_input(tmp_path, monkeypatch, capsys, configured):
    monkeypatch.setenv("ELYS_DATA_DIR", str(tmp_path))
    api_hash = "0123456789abcdef0123456789abcdef"
    if configured:
        wizard.save_keys(tmp_path / "settings.toml", 42, api_hash)
    keys = "" if configured else f"42\n{api_hash}\n"
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(keys + "2\n+79991234567\n12345\n"))
    user = User(id=1, first_name="Test")
    client = SimpleNamespace(
        send_phone_number_code=AsyncMock(
            return_value=SimpleNamespace(type=enums.SentCodeType.APP, phone_code_hash="hash")
        ),
        sign_in=AsyncMock(return_value=user),
    )

    class App:
        def __init__(self, config, *, login):
            assert config.api_id == 42
            self.login = login

        async def run(self):
            assert await self.login(client) is user

    monkeypatch.setattr(app, "App", App)
    monkeypatch.setattr(cli.log, "setup", Mock())
    cli.main([])
    client.send_phone_number_code.assert_awaited_once_with("+79991234567")
    client.sign_in.assert_awaited_once_with("+79991234567", "hash", "12345")
    out = capsys.readouterr().out
    assert "Вход выполнен: Test" in out
    assert "\x1b" not in out


@pytest.mark.parametrize("configured", [False, True])
def test_closed_input_has_actionable_message(tmp_path, monkeypatch, configured):
    monkeypatch.setenv("ELYS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(""))
    if configured:
        wizard.save_keys(tmp_path / "settings.toml", 42, "0123456789abcdef0123456789abcdef")

    class App:
        def __init__(self, config, *, login):
            self.login = login

        async def run(self):
            await self.login(None)  # EOF в меню, до обращения к Telegram

    monkeypatch.setattr(app, "App", App)
    monkeypatch.setattr(cli.log, "setup", Mock())
    with pytest.raises(SystemExit, match=r"Ввод закрыт.*Включи ввод в консоли панели"):
        cli.main([])


def test_bot_setup_failure_has_actionable_message(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "load", lambda: settings.Settings(api_id=1, api_hash="h", data_dir=tmp_path))
    monkeypatch.setattr(cli.log, "setup", Mock())

    class BrokenApp:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self):
            raise cli.BotSetupError("Открой @BotFather и проверь ограничения.")

    monkeypatch.setattr(app, "App", BrokenApp)
    with pytest.raises(SystemExit, match=r"Не удалось настроить бота-помощника.*BotFather"):
        cli.main([])


async def test_failed_logout_stops_client(tmp_path, monkeypatch):
    client = Mock(
        start=AsyncMock(), log_out=AsyncMock(side_effect=errors.FloodWait(1)), stop=AsyncMock(), is_initialized=True
    )
    monkeypatch.setattr(cli.clients, "user", lambda *a, **kw: client)
    with pytest.raises(errors.FloodWait):
        await cli.logout(settings.Settings(api_id=1, api_hash="h", data_dir=tmp_path))
    client.stop.assert_awaited_once()
