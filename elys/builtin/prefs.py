from pyrogram import Client
from pyrogram.types import Message

from elys import E, Module, UserError, html, respond

module = Module("Prefs")


@module.command("prefs")
async def prefs(client: Client, message: Message):
    # — настройки; без аргументов покажет примеры
    app = module.app
    router, core = app.router, app.kv.ns("core")
    args = message.command[1:]
    p = router.prefixes[0]
    if not args:
        aliases = ", ".join(f"{k} → {v}" for k, v in router.aliases.items()) or "нет"
        await respond(message, f"{E.gear} <b>Elys · настройки</b>\n\n"
                      f"<blockquote>Начало команды: {html.code(' '.join(router.prefixes))}\n"
                      f"Язык: {html.code(app.language)}\n"
                      f"Картинки: {'включены' if app.banners_enabled else 'выключены'}\n"
                      f"Сокращения: {html.escape(aliases)}</blockquote>\n\n"
                      "<b>Изменить</b>\n"
                      f"<blockquote>{html.code(p + 'prefs prefix !')} — команды с !\n"
                      f"{html.code(p + 'prefs prefix . !')} — оба варианта\n"
                      f"{html.code(p + 'prefs language ru')} — язык: ru / en\n"
                      f"{html.code(p + 'prefs banners off')} — картинки: on / off\n"
                      f"{html.code(p + 'prefs alias п ping')} — {html.code(p + 'п')} вместо {html.code(p + 'ping')}\n"
                      f"{html.code(p + 'prefs unalias п')} — убрать сокращение</blockquote>\n\n"
                      "<i>Сохраняется автоматически.</i>")
        return
    key, *values = args
    try:
        if key == "prefix" and values:
            router.prefixes = values
            core["prefixes"] = list(router.prefixes)
        elif key == "language" and len(values) == 1 and values[0] in {"ru", "en"}:
            app.language = core["language"] = values[0]
        elif key == "banners" and values in (["on"], ["off"]):
            app.banners_enabled = core["banners"] = values == ["on"]
        elif key == "alias" and len(values) == 2:
            name, target = values
            command = router.get(target.lower())
            if command is None:
                raise UserError(f"Команды {target} нет. Посмотри список: {p}help")
            router.set_aliases({**router.aliases, name.lower(): command.name})
            core["aliases"] = router.aliases
        elif key == "unalias" and len(values) == 1:
            name = values[0].lower()
            if name not in router.aliases:
                raise UserError(f"Такого сокращения нет. Список: {p}prefs")
            router.set_aliases({k: v for k, v in router.aliases.items() if k != name})
            core["aliases"] = router.aliases
        else:
            raise UserError(f"Покажу варианты и готовые примеры: напиши {p}prefs")
    except ValueError as exc:
        raise UserError(f"{exc}. Примеры: {p}prefs") from None
    await respond(message, f"{E.check} <b>Сохранено</b>\n"
                  f"<blockquote>Настройки → {html.code(router.prefixes[0] + 'prefs')}</blockquote>")


@module.loop(1800)
async def refresh_premium(client: Client):
    module.app.premium = bool((await client.get_me()).is_premium)


@module.on_ready
async def ready(client: Client):
    refresh_premium.start()
