import asyncio
import random
from sqlite3 import ProgrammingError

import pytest

from elys.storage.sqlite import SafeSQLiteStorage


async def test_concurrent_peer_writes_do_not_hit_sqlite_misuse(tmp_path):
    # Без закрытия курсоров 14–18 из 20 параллельных задач падали с InterfaceError «API misuse».
    storage = SafeSQLiteStorage("t", workdir=tmp_path)
    await storage.open()

    async def work():
        for _ in range(200):
            ids = [-1000000000000 - random.randrange(10**9) for _ in range(50)]
            await storage.update_peers([(i, random.randrange(2**62), "channel", None) for i in ids])
            await storage.update_usernames([(i, [f"u{i}"]) for i in ids])

    try:
        await asyncio.gather(*(work() for _ in range(20)))
    finally:
        await storage.close()


async def test_write_cursors_are_closed_and_reads_still_work(tmp_path):
    storage = SafeSQLiteStorage("t", workdir=tmp_path)
    await storage.open()
    try:
        cursor = await storage.conn.executemany("REPLACE INTO usernames (id, username) VALUES (?, ?)", [(1, "a")])
        with pytest.raises(ProgrammingError):
            await cursor.fetchall()
        rows = await (await storage.conn.execute("SELECT id, username FROM usernames")).fetchall()
        assert [tuple(r) for r in rows] == [(1, "a")]
    finally:
        await storage.close()
