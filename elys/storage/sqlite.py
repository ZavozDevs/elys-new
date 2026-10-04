"""SQLite-хранилище сессии wzgram без гонки курсоров."""

from __future__ import annotations

from pyrogram.storage import SQLiteStorage


class SafeSQLiteStorage(SQLiteStorage):
    # wzgram 3.1.3 + aiosqlite 0.22 не закрывают курсоры после записи. Курсор освобождается в
    # потоке событий, пока поток базы выполняет другой запрос, и при параллельных ответах
    # Telegram запись падает: sqlite3.InterfaceError «bad parameter or other API misuse»
    # («Failed to fetch peers from chats»). Закрываем курсоры записи в потоке самой базы.
    async def open(self) -> None:
        await super().open()
        conn = self.conn
        if conn is None:
            return
        execute, executemany = conn.execute, conn.executemany

        async def safe_executemany(sql, parameters=None):
            cursor = await executemany(sql, parameters if parameters is not None else [])
            await cursor.close()
            return cursor

        async def safe_execute(sql, parameters=None):
            cursor = await execute(sql, parameters)
            if not sql.lstrip().upper().startswith(("SELECT", "PRAGMA")):
                await cursor.close()
            return cursor

        conn.executemany, conn.execute = safe_executemany, safe_execute
