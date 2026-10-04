"""kv: всё в памяти, запись в sqlite пачкой через `delay` после первого изменения."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

import aiosqlite

from .files import private_file

log = logging.getLogger(__name__)

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
CREATE TABLE IF NOT EXISTS kv (
    ns    TEXT NOT NULL,
    key   TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (ns, key)
) WITHOUT ROWID;
"""
_UPSERT = "INSERT INTO kv (ns, key, value) VALUES (?, ?, ?) ON CONFLICT (ns, key) DO UPDATE SET value = excluded.value"
_DELETE = "DELETE FROM kv WHERE ns = ? AND key = ?"


class KV:
    def __init__(self, conn: aiosqlite.Connection, data: dict[str, dict[str, Any]], delay: float) -> None:
        self._conn = conn
        self._data = data
        self._delay = delay
        self._dirty: set[tuple[str, str]] = set()
        self._spaces: dict[str, Namespace] = {}
        self._lock = asyncio.Lock()
        self._timer: asyncio.Task[None] | None = None
        self._closed = False

    @classmethod
    async def open(cls, path: str | Path, *, delay: float = 0.5) -> KV:
        if str(path) != ":memory:":
            private_file(Path(path))
        conn = await aiosqlite.connect(path)
        try:
            await conn.executescript(_SCHEMA)
            data: dict[str, dict[str, Any]] = {}
            async with conn.execute("SELECT ns, key, value FROM kv") as cursor:
                async for ns, key, value in cursor:
                    data.setdefault(ns, {})[key] = json.loads(value)
        except BaseException:
            await conn.close()
            raise
        return cls(conn, data, delay)

    def ns(self, name: str) -> Namespace:
        self.ensure_open()
        if not isinstance(name, str):
            raise TypeError("namespace должен быть строкой")
        space = self._spaces.get(name)
        if space is None:
            space = self._spaces[name] = Namespace(self, name, self._data.setdefault(name, {}))
        return space

    def mark(self, ns: str, key: str) -> None:
        self._dirty.add((ns, key))
        if self._timer is None:
            self._timer = asyncio.get_running_loop().create_task(self._flush_later())

    async def _flush_later(self) -> None:
        await asyncio.sleep(self._delay)
        self._timer = None
        try:
            await self.flush()
        except Exception:
            log.exception("kv: запись не удалась, повтор при следующем изменении")

    async def flush(self) -> None:
        async with self._lock:
            if not self._dirty:
                return
            batch, self._dirty = self._dirty, set()
            upserts, deletes = [], []
            try:
                for ns, key in batch:
                    space = self._data.get(ns, {})
                    if key not in space:
                        deletes.append((ns, key))
                        continue
                    # Сериализация остаётся пакетной. Невалидные правки на месте
                    # не теряем: вся пачка остаётся dirty, flush сообщает ошибку.
                    _validate(space[key])
                    value = json.dumps(space[key], ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    upserts.append((ns, key, value))
                await self._conn.executemany(_UPSERT, upserts)
                await self._conn.executemany(_DELETE, deletes)
                await self._conn.commit()
            except BaseException:
                self._dirty |= batch
                await self._conn.rollback()
                raise

    def ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("KV закрыт")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._timer is not None:
            self._timer.cancel()
            await asyncio.gather(self._timer, return_exceptions=True)
            self._timer = None
        try:
            await self.flush()
        finally:
            await self._conn.close()


def _validate(value: Any, seen: set[int] | None = None) -> None:
    """Только JSON-типы: без неявного преобразования tuple и ключей словаря."""
    kind = type(value)
    if value is None or kind in (str, int, bool):
        return
    if kind is float and math.isfinite(value):
        return
    if kind not in (list, dict):
        raise TypeError("KV принимает только JSON: null, bool, str, int, конечный float, list и dict[str, ...]")
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        raise ValueError("циклическое значение KV")
    seen.add(identity)
    try:
        if kind is dict:
            if any(type(key) is not str for key in value):
                raise TypeError("ключи JSON-объекта должны быть строками")
            value = value.values()
        for item in value:
            _validate(item, seen)
    finally:
        seen.remove(identity)


class Namespace(MutableMapping[str, Any]):
    """JSON-словарь. set/touch валидируют сразу; сериализация и запись — пачкой.

    Правку на месте (`db[k].append`) обязательно отметить через touch(k).
    """

    __slots__ = ("_data", "_kv", "name")

    def __init__(self, kv: KV, name: str, data: dict[str, Any]) -> None:
        self._kv = kv
        self._data = data
        self.name = name

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._kv.ensure_open()
        if not isinstance(key, str):
            raise TypeError("ключ KV должен быть строкой")
        _validate(value)
        self._data[key] = value
        self._kv.mark(self.name, key)

    def __delitem__(self, key: str) -> None:
        self._kv.ensure_open()
        del self._data[key]
        self._kv.mark(self.name, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    set = __setitem__

    def touch(self, key: str) -> None:
        self._kv.ensure_open()
        _validate(self._data[key])
        self._kv.mark(self.name, key)

    async def flush(self) -> None:
        await self._kv.flush()

    def __repr__(self) -> str:
        return f"Namespace({self.name!r}, {self._data!r})"
