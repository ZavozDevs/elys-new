import inspect

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, E, Module, UserError, html, raw_args, respond

module = Module("Help", config=Config(banner=Config.url(doc="Картинка над справкой; пусто — без картинки")), strings={
    "ru": {
        "intro": "{e:info} <b>Elys · команды</b>\n"
                 "Команда — обычное сообщение с <code>{p}</code> в начале. Только от тебя.",
        "next": "Описание → <code>{p}help Ping</code>\nНастройки → <code>{p}prefs</code>",
        "author": "Автор: {author}",
        "background": "Работает в фоне, без команд.",
        "listens_all": "{e:warn_security} Слушает все сообщения — без ограничения области работы.",
        "arguments": "Вместо &lt;…&gt; подставь свой текст; […] — необязательная часть.",
    },
    "en": {
        "intro": "{e:info} <b>Elys · commands</b>\n"
                 "Elys — your account assistant. Send a message starting with <code>{p}</code>. "
                 "Only you can run commands.",
        "next": "Details → <code>{p}help Ping</code>\nSettings → <code>{p}prefs</code>",
        "author": "Author: {author}",
        "background": "Runs in the background, no commands.",
        "listens_all": "{e:warn_security} Listens to all messages — no scope restriction.",
        "arguments": "Replace &lt;…&gt; with your text; […] is optional.",
    },
})


def describe(command, prefix):
    doc = command.callback.__doc__
    if not doc:
        try:
            # в builtin описание — первый комментарий, в сторонних модулях — docstring.
            doc = next((line.strip()[1:].strip() for line in inspect.getsource(command.callback).splitlines()
                        if line.strip().startswith("#")), "")
        except (OSError, TypeError):
            doc = ""
    doc = (doc or "описание пока не добавлено автором").strip().splitlines()[0].lstrip("— ")
    aliases = ", ".join(prefix + name for name in command.aliases)
    suffix = f" ({html.escape(aliases)})" if aliases else ""
    return f"{html.code(prefix + command.name)} — {html.escape(doc)}{suffix}"


@module.command("help", aliases=("h",))
async def help_command(client: Client, message: Message):
    # — справка; пример: .help Ping
    query = raw_args(message).strip()
    app, p = module.app, module.app.router.prefixes[0]
    if not query:
        commands = []
        for item in app.modules.values():
            if item.commands:
                names = " · ".join(html.code(p + command.name) for command in item.commands)
                commands.append(f"{html.b(item.name)} — {names}")
        listing = "\n".join(commands)
        text = f"{module.t('intro', p=p)}\n\n<blockquote>{listing}</blockquote>\n\n{module.t('next', p=p)}"
        return await respond(message, text, banner=module.config["banner"])
    item = app.loader.resolve(query)
    command = app.router.get(query.removeprefix(p))
    if item is None and command is not None:
        item = command.owner
    if item is None:
        raise UserError(f"Такого модуля или команды нет. Напиши {p}help — покажу список.")
    header = f"{E['module']} {html.b(item.name)} · {html.escape(item.version)}"
    if item.author:
        header += "\n" + module.t("author", author=item.author)
    descriptions = "\n".join(describe(c, p) for c in item.commands)
    lines = [header, f"<blockquote>{descriptions or module.t('background')}</blockquote>"]
    if "&lt;" in descriptions or "[" in descriptions:
        lines.append(module.t("arguments"))
    if item.listens_all:
        lines.append(module.t("listens_all"))
    await respond(message, "\n\n".join(lines), banner=item.banner)
