"""Драйвер бенчмарка: шлёт .ping в «Избранное» и ждёт правки. Работает на КОПИИ сессии.

    bench_drive.py LIB SESSION API_ID API_HASH COUNT TIMEOUT

LIB: pyrogram | telethon. Печатает JSON: {"ok": n, "lat_ms": [...]}.
COUNT=1 + большой TIMEOUT — ждать первого ответа (готовность бота).
"""

import asyncio
import json
import sys
import time

LIB, SESSION, API_ID, API_HASH, COUNT, TIMEOUT = sys.argv[1:7]
API_ID, COUNT, TIMEOUT = int(API_ID), int(COUNT), float(TIMEOUT)
POLL = 0.01


async def measure(send, fetch):
    lat, deadline = [], time.monotonic() + TIMEOUT
    while len(lat) < COUNT and time.monotonic() < deadline:
        msg = await send()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 10:
            await asyncio.sleep(POLL)
            if await fetch(msg) != ".ping":
                lat.append(round((time.monotonic() - t0) * 1000))
                break
        await asyncio.sleep(1.5)
    return {"ok": len(lat), "lat_ms": lat}


async def pyrogram():
    from pyrogram import Client

    c = Client(SESSION, api_id=API_ID, api_hash=API_HASH, workdir=".", no_updates=True)
    await c.start()
    try:

        async def fetch(m):
            cur = await c.get_messages("me", m.id)
            return None if cur is None or cur.empty else cur.text

        return await measure(lambda: c.send_message("me", ".ping"), fetch)
    finally:
        await c.stop()


async def telethon():
    from elystl import TelegramClient

    c = TelegramClient(SESSION, API_ID, API_HASH, receive_updates=False)
    await c.connect()
    try:

        async def fetch(m):
            cur = await c.get_messages("me", ids=m.id)
            return None if cur is None else cur.raw_text

        return await measure(lambda: c.send_message("me", ".ping"), fetch)
    finally:
        await c.disconnect()


print(json.dumps(asyncio.run(pyrogram() if LIB == "pyrogram" else telethon())))
