from pyrogram import Client

from elys import Module

module = Module("Welcome")

TEXT = """🌟 Elys работает!

В Telegram напиши {p}ping — проверить связь.
  {p}help   — команды
  {p}prefs  — настройки

Команды работают в любом чате, только из твоих сообщений.
Ответы видны участникам чата. Для личного используй «Избранное»."""


@module.on_load
async def greet(client: Client) -> None:
    # один раз. в «Избранное» не пишем — это личное место пользователя;
    # до появления форума (этап 3) — в терминал
    if module.db.get("shown"):
        return
    module.log.info(TEXT.format(p=module.app.router.prefixes[0]))
    module.db["shown"] = True
