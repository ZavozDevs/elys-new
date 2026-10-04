from time import perf_counter

from pyrogram import Client
from pyrogram.types import Message

from elys import Module, respond

module = Module("Ping")


@module.command("ping")
async def ping(client: Client, message: Message) -> None:
    # — задержка ответа telegram
    start = perf_counter()
    reply = await respond(message, "🏓")
    ms = (perf_counter() - start) * 1000
    await respond(reply, f"🏓 <b>Понг</b> <code>{ms:.0f} мс</code>")
