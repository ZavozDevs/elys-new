from pyrogram import Client

from elys import Module

module = Module("Welcome", author="Elys")

TEXT = """🌟 Elys работает!

Elys — помощник внутри твоего аккаунта Telegram.
Команда — это сообщение, которое начинается с {p}. Писать можно в любом чате.

Попробуй: напиши {p}ping — Elys ответит, сколько времени занял ответ Telegram.

Команды выполняются только из твоих сообщений: собеседники не могут ими управлять."""


@module.on_load
async def greet(client: Client) -> None:
    # один раз. в «Избранное» не пишем — это личное место пользователя;
    # до появления форума (этап 3) — в терминал
    if module.db.get("shown"):
        return
    module.log.info(TEXT.format(p=module.app.router.prefixes[-1]))
    module.db["shown"] = True
