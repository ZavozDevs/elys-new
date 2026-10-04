import tempfile
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from elys import E, LoadError, Module, UserError, get_reply, html, respond

module = Module("Modules")


def prefix():
    return module.app.router.prefixes[0]


async def perform(message, operation):
    try:
        await respond(message, module.t("working"))
        item = await operation
    except LoadError as exc:
        raise UserError(str(exc).replace(".lm", prefix() + "lm")) from None
    except Exception as exc:
        module.log.exception("не удалось изменить модуль")
        # детали стороннего кода — в лог, а не в переписку (там могут быть ключи).
        raise UserError(f"Не удалось изменить модуль. Подробности — в файле elys.log. "
                        f"Проверь файл и попробуй снова; список: {prefix()}lm") from exc
    finally:
        operation.close()  # не оставляем корутину, если промежуточный ответ не отправился
    await respond(message, module.t("loaded", name=item.name, p=prefix()), banner=item.banner)


@module.command("dlm")
async def download(client: Client, message: Message):
    # <ссылка или путь> --trust — установить модуль; можно ответить на файл .py
    args = message.command[1:]
    p = prefix()
    if "--trust" not in args:
        await respond(message, f"{E['module']} <b>Добавить модуль</b>\n\n"
                      f"<blockquote>{html.code(p + 'dlm --trust')} — в ответ на файл .py\n"
                      f"{html.code(p + 'dlm <ссылка или путь> --trust')} — по адресу</blockquote>\n"
                      "Вместо &lt;…&gt; — адрес твоего файла.\n\n"
                      f"{E.warn_security} Модуль и его зависимости получают полный доступ к аккаунту и компьютеру.\n"
                      "<b>Устанавливай только доверенный код.</b> "
                      "<code>--trust</code> — твоё согласие, не проверка безопасности.")
        return
    args = [arg for arg in args if arg != "--trust"]
    if len(args) > 1:
        raise UserError(f"Нужен один путь или ссылка. Путь с пробелами возьми в кавычки. Примеры: {p}dlm")
    if args:
        await perform(message, module.app.loader.install(args[0], trusted=True))
        return
    reply = await get_reply(message)
    document = getattr(reply, "document", None)
    if document is None or not (document.file_name or "").endswith(".py"):
        raise UserError(f"Ответь на файл .py командой {p}dlm --trust или укажи ссылку. Примеры: {p}dlm")
    if document.file_size and document.file_size > 2 * 1024 * 1024:
        raise UserError("Файл больше 2 МБ. Попроси автора прислать небольшой модуль .py.")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / Path(document.file_name).name
        await client.download_media(reply, file_name=str(path))
        await perform(message, module.app.loader.install(path, trusted=True))


@module.command("lm")
async def load(client: Client, message: Message):
    # [имя файла] — список модулей или включение ранее выключенного
    args = message.command[1:]
    app, p = module.app, prefix()
    if args:
        if len(args) != 1:
            raise UserError(f"Нужно одно имя файла без .py: {p}lm hello")
        await perform(message, app.loader.load(args[0]))
        return
    lines = [f"{E['module']} <b>Elys · модули</b>"]
    builtins = [item.name for item in app.modules.values() if item.name not in app.loader.sources]
    installed = [item.name for item in app.modules.values() if item.name in app.loader.sources]
    for title, names in (("Встроенные", builtins), ("Установленные", installed)):
        if names:
            lines.append(f"<b>{title} · {len(names)}</b>\n" + html.quote(" · ".join(names)))
    disabled = app.kv.ns("core").get("disabled_modules", [])
    if disabled:
        commands = "\n".join(html.code(p + 'lm ' + name) for name in disabled)
        lines.append(f"<b>Выключены · {len(disabled)}</b>\n<blockquote>{commands}</blockquote>\n"
                     "Напиши команду выше, чтобы включить.")
    lines.append(f"Добавить → {html.code(p + 'dlm')}\n"
                 f"Команды → {html.code(p + 'help Ping')}\n"
                 f"Выключить → {html.code(p + 'ulm Hello')}")
    await respond(message, "\n\n".join(lines))


@module.command("ulm")
async def unload(client: Client, message: Message):
    # <модуль> [--purge --yes] — выключить; purge также стирает его настройки и данные
    args = message.command[1:]
    purge = "--purge" in args
    names = [arg for arg in args if arg not in {"--purge", "--yes"}]
    if len(names) != 1:
        raise UserError(f"Укажи модуль, например: {prefix()}ulm Hello. Имена: {prefix()}lm")
    if purge and "--yes" not in args:
        raise UserError(f"Это сотрёт настройки и данные модуля без возможности вернуть их. "
                        f"Если уверен: {prefix()}ulm {names[0]} --purge --yes")
    loader = module.app.loader
    item = loader.resolve(names[0])
    source = loader.sources.get(item.name) if item else None
    try:
        item = await loader.unload(names[0], purge=purge)
    except LoadError as exc:
        raise UserError(str(exc).replace(".lm", prefix() + "lm")) from None
    if purge:
        text = (f"{E.check} {html.b(item.name)} · выключен\n"
                "<blockquote>Настройки и данные стёрты безвозвратно. Файл оставлен.\n"
                f"Включить заново → {html.code(prefix() + 'lm ' + source.stem)}</blockquote>")
    else:
        text = module.t("unloaded", name=item.name, p=prefix(), file=source.stem)
    await respond(message, text)


@module.command("reload")
async def reload_module(client: Client, message: Message):
    # <модуль> — перечитать код с диска
    if len(message.command) != 2:
        raise UserError(f"Укажи модуль: {prefix()}reload Hello. Список: {prefix()}lm")
    await perform(message, module.app.loader.reload(message.command[1]))


@module.command("rollback")
async def rollback(client: Client, message: Message):
    # <модуль> — вернуть код предыдущей версии (данные не откатываются)
    if len(message.command) != 2:
        raise UserError(f"Укажи модуль: {prefix()}rollback Hello. Список: {prefix()}lm")
    await perform(message, module.app.loader.reload(message.command[1], rollback=True))
