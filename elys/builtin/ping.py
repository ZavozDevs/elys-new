from time import perf_counter

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, respond

module = Module("Ping", config=Config(banner=Config.url(doc="Картинка над ответом")))


@module.command("ping")
async def ping(client: Client, message: Message) -> None:
    # — задержка ответа telegram
    start = perf_counter()
    reply = await respond(message, "🏓")
    ms = (perf_counter() - start) * 1000
    await respond(reply, f"🏓 <b>Понг</b>\n<blockquote>Ответ Telegram · <code>{ms:.0f} мс</code></blockquote>",
                  banner=module.config["banner"])
