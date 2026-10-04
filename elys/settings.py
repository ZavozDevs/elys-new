# настройки: data/settings.toml (его пишет мастер первого запуска), поверх — переменные ELYS_<ПОЛЕ>.

from __future__ import annotations

import json
import logging
import math
import os
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from elys.storage.files import private_directory, protect_existing


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


def _prefixes(value: Any) -> tuple[str, ...]:
    # в env — через пробел: ELYS_PREFIXES=". !"
    if isinstance(value, str):
        value = value.split()
    if not isinstance(value, list) or not value or not all(
        isinstance(p, str) and p and not any(c.isspace() for c in p) for p in value
    ):
        raise ValueError("prefixes: нужен непустой список строк без пробелов")
    return tuple(dict.fromkeys(value))


def _log_level(value: Any) -> str:
    if not isinstance(value, str) or value.upper() not in logging.getLevelNamesMapping():
        raise ValueError("log_level: нужен уровень DEBUG, INFO, WARNING, ERROR или CRITICAL")
    return value.upper()


def _api_id(value: Any) -> int:
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        value = int(value)
    if type(value) is not int or value <= 0:
        raise ValueError("api_id: нужно положительное целое число")
    return value


def _api_hash(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("api_hash: нужна непустая строка")
    return value.strip()


def _table(value: Any) -> dict[str, dict[str, float]]:
    # в env — json; в settings.toml — обычная таблица.
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("rate_limits: ожидается таблица")
    for category, limits in value.items():
        if not isinstance(limits, dict) or limits.keys() - {"rate", "burst"}:
            raise ValueError(f"rate_limits.{category}: допустимы только rate и burst")
        if any(type(n) not in (int, float) or not math.isfinite(n) or n <= 0 for n in limits.values()):
            raise ValueError(f"rate_limits.{category}: нужны положительные конечные числа")
    return value


_CAST: dict[str, Callable[[Any], Any]] = {
    "api_id": _api_id,
    "api_hash": _api_hash,
    "prefixes": _prefixes,
    "log_level": _log_level,
    "rate_limits": _table,
}


def load(env: Mapping[str, str] = os.environ) -> Settings:
    directory = data_dir(env)
    path = settings_file(directory)
    try:
        private_directory(directory)
        protect_existing(path)
        values: dict[str, Any] = tomllib.loads(path.read_text("utf-8")) if path.is_file() else {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise SettingsError(f"{path}: {e}") from None

    for name in _CAST:
        if (value := env.get(f"ELYS_{name.upper()}")) is not None:
            values[name] = value

    if unknown := values.keys() - _CAST.keys():
        raise SettingsError(f"{path}: неизвестные поля {', '.join(sorted(unknown))}")
    if "api_id" not in values or "api_hash" not in values:
        raise MissingKeys(path)

    try:
        return Settings(data_dir=directory, **{name: _CAST[name](value) for name, value in values.items()})
    except (TypeError, ValueError) as e:
        raise SettingsError(f"{path}: {e}") from None
