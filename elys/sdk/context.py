# контекст команды наследуется её задачами; настройки читаются при каждом ответе.

from contextvars import ContextVar
from typing import Any

current: ContextVar[Any] = ContextVar("elys_host", default=None)


def premium() -> bool:
    return bool(getattr(current.get(), "premium", False))
