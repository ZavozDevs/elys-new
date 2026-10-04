from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, respond

module = Module(
    "Hello",
    version="1.0",
    config=Config(greeting=Config.value("Привет", doc="Начало приветствия")),
    strings={"ru": {"hello": "{e:check} {greeting}, {name}!"},
             "en": {"hello": "{e:check} Hello, {name}!"}},
)


@module.command("hello", aliases=("привет",))
async def hello(client: Client, message: Message):
    # [имя] — поздороваться; пример: .hello Маша
    name = " ".join(message.command[1:]) or "друг"
    await respond(message, module.t("hello", greeting=module.config["greeting"], name=name))
