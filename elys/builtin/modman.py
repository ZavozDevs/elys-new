import tempfile
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from elys import LoadError, Module, UserError, get_reply, html, respond

module = Module("Modules")
t = module.t


def prefix():
    return module.app.router.prefixes[0]


def need(ok, key, **values):
    if not ok:
        raise UserError(t(key, **values))


async def perform(message, operation):
    try:
        await respond(message, t("working"))
        item = await operation
    except LoadError as exc:
        raise UserError(str(exc).replace(".lm", prefix() + "lm")) from None
    except Exception as exc:
        module.log.exception("не удалось изменить модуль")
        # детали стороннего кода — в лог, а не в переписку (там могут быть ключи).
        raise UserError(t("failed")) from exc
    finally:
        operation.close()  # не оставляем корутину, если промежуточный ответ не отправился
    await respond(message, t("loaded", name=item.name), banner=item.banner)


@module.command("dlm", roles=("sudo",))
async def download(client: Client, message: Message):
    # <ссылка или путь> --trust — установить модуль; можно ответить на файл .py
    args = message.command[1:]
    if "--trust" not in args:
        return await respond(message, t("dlm"))
    args = [arg for arg in args if arg != "--trust"]
    need(len(args) <= 1, "one_path")
    if args:
        return await perform(message, module.app.loader.install(args[0], trusted=True))
    reply = await get_reply(message)
    document = getattr(reply, "document", None)
    need(document and (document.file_name or "").endswith(".py"), "reply_file")
    need((document.file_size or 0) <= 2 * 1024 * 1024, "too_big")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / Path(document.file_name).name
        await client.download_media(reply, file_name=str(path))
        await perform(message, module.app.loader.install(path, trusted=True))


@module.command("lm", roles=("sudo",))
async def load(client: Client, message: Message):
    # [имя файла] — список модулей или включение ранее выключенного
    args, app = message.command[1:], module.app
    if args:
        need(len(args) == 1, "one_name")
        return await perform(message, app.loader.load(args[0]))
    names, sources = [item.name for item in app.modules.values()], app.loader.sources
    groups = {
        "builtin": [n for n in names if n not in sources],
        "installed": [n for n in names if n in sources],
        "disabled": app.kv.ns("core").get("disabled_modules", []),
    }
    lines = [t("list")]
    for key, group in groups.items():
        if group:
            codes = html.Html("\n".join(html.code(f"{prefix()}lm {n}") for n in group))
            body = codes if key == "disabled" else " · ".join(group)
            lines.append(t(key, n=len(group), names=html.quote(body)))
    await respond(message, "\n\n".join([*lines, t("hints")]))


@module.command("ulm", roles=("sudo",))
async def unload(client: Client, message: Message):
    # <модуль> [--purge --yes] — выключить; purge также стирает его настройки и данные
    args = message.command[1:]
    purge = "--purge" in args
    names = [arg for arg in args if arg not in {"--purge", "--yes"}]
    need(len(names) == 1, "ulm")
    need(not purge or "--yes" in args, "purge_confirm", name=names[0])
    loader = module.app.loader
    item = loader.resolve(names[0])
    source = loader.sources.get(item.name) if item else None
    try:
        item = await loader.unload(names[0], purge=purge)
    except LoadError as exc:
        raise UserError(str(exc).replace(".lm", prefix() + "lm")) from None
    await respond(message, t("purged" if purge else "unloaded", name=item.name, file=source.stem))


@module.command("reload", roles=("sudo",))
async def reload_module(client: Client, message: Message):
    # <модуль> — перечитать код с диска
    need(len(message.command) == 2, "reload")
    await perform(message, module.app.loader.reload(message.command[1]))


@module.command("rollback", roles=("sudo",))
async def rollback(client: Client, message: Message):
    # <модуль> — вернуть код предыдущей версии (данные не откатываются)
    need(len(message.command) == 2, "rollback")
    await perform(message, module.app.loader.reload(message.command[1], rollback=True))
