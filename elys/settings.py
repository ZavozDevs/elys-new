"""настройки: data/settings.toml (его пишет мастер первого запуска), поверх — переменные ELYS_<ПОЛЕ>."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SettingsError(Exception):
    pass


class MissingKeys(SettingsError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class Settings:
    api_id: int
    api_hash: str
    data_dir: Path = Path("data")
    prefixes: tuple[str, ...] = (".",)
    log_level: str = "INFO"
    rate_limits: dict[str, dict[str, float]] = field(default_factory=dict)  # {} — лимиты wzgram по умолчанию

    @property
    def file(self) -> Path:
        return settings_file(self.data_dir)


def data_dir(env: Mapping[str, str] = os.environ) -> Path:
    return Path(env.get("ELYS_DATA_DIR", "data"))


def settings_file(directory: Path) -> Path:
    return directory / "settings.toml"


def _prefixes(value: str | list[str]) -> tuple[str, ...]:
    # в env — через пробел: ELYS_PREFIXES=". !"
    return tuple(value.split() if isinstance(value, str) else value)


def _table(value: Any) -> dict:
    if not isinstance(value, dict):
        raise TypeError("rate_limits: ожидается таблица")
    return value


_CAST: dict[str, Callable[[Any], Any]] = {
    "api_id": int,
    "api_hash": str,
    "prefixes": _prefixes,
    "log_level": lambda v: str(v).upper(),
    "rate_limits": _table,
}


def load(env: Mapping[str, str] = os.environ) -> Settings:
    directory = data_dir(env)
    path = settings_file(directory)
    try:
        values: dict[str, Any] = tomllib.loads(path.read_text("utf-8")) if path.is_file() else {}
    except tomllib.TOMLDecodeError as e:
        raise SettingsError(f"{path}: {e}") from None

    for name in _CAST:
        if (value := env.get(f"ELYS_{name.upper()}")) is not None:
            values[name] = value

    if unknown := values.keys() - _CAST.keys():
        raise SettingsError(f"{path}: неизвестные поля {', '.join(sorted(unknown))}")
    if not values.get("api_id") or not values.get("api_hash"):
        raise MissingKeys(path)

    try:
        return Settings(data_dir=directory, **{name: _CAST[name](value) for name, value in values.items()})
    except (TypeError, ValueError) as e:
        raise SettingsError(f"{path}: {e}") from None
