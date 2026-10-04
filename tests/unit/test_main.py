from unittest.mock import AsyncMock, Mock

import pytest
from pyrogram import errors

from elys import __main__ as cli
from elys import settings, wizard


def test_second_settings_error_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    load = Mock(side_effect=[settings.MissingKeys(tmp_path), settings.SettingsError("bad")])
    monkeypatch.setattr(settings, "load", load)
    monkeypatch.setattr(wizard, "ask_keys", Mock())
    with pytest.raises(SystemExit, match="Ошибка в настройках: bad"):
        cli.main([])


async def test_failed_logout_stops_client(tmp_path, monkeypatch):
    client = Mock(
        start=AsyncMock(), log_out=AsyncMock(side_effect=errors.FloodWait(1)), stop=AsyncMock(), is_initialized=True
    )
    monkeypatch.setattr(cli.clients, "user", lambda *a, **kw: client)
    with pytest.raises(errors.FloodWait):
        await cli.logout(settings.Settings(api_id=1, api_hash="h", data_dir=tmp_path))
    client.stop.assert_awaited_once()
