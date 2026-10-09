import inspect

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, E, Module, UserError, html, raw_args, respond

BANNER = "https://raw.githubusercontent.com/ZavozDevs/assets/main/elys_userbot/cmd.png"

module = Module("Help", config=Config(banner=Config.url(BANNER, doc="Картинка над справкой")), strings={
    "ru": {
        "intro": "{e:info} <b>Elys · команды</b>\n"
                 "Команда — обычное сообщение с <code>{p}</code> в начале.",
        "author": "Автор: {author}",
        "background": "Работает в фоне, без команд.",
        "listens_all": "{e:warn} Слушает все сообщения — без ограничения области работы.",
        "arguments": "Вместо &lt;…&gt; подставь свой текст; […] — необязательная часть.",
    },
    "en": {
        "intro": "{e:info} <b>Elys · commands</b>\n"
                 "Elys — your account assistant. Send a message starting with <code>{p}</code>.",
        "author": "Author: {author}",
        "background": "Runs in the background, no commands.",
        "listens_all": "{e:warn} Listens to all messages — no scope restriction.",
        "arguments": "Replace &lt;…&gt; with your text; […] is optional.",
    },
})


def explain(command):
    doc = command.callback.__doc__
    if not doc:
        try:
            # в builtin описание — первый комментарий, в сторонних модулях — docstring.
            doc = next((line.strip()[1:].strip() for line in inspect.getsource(command.callback).splitlines()
                        if line.strip().startswith("#")), "")
        except (OSError, TypeError):
            doc = ""
    return (doc or "описание пока не добавлено автором").strip().splitlines()[0].lstrip("— ")


def describe(command, prefix):
    doc = explain(command)
    aliases = ", ".join(prefix + name for name in command.aliases)
    suffix = f" ({html.escape(aliases)})" if aliases else ""
    return f"{html.code(prefix + command.name)} — {html.escape(doc)}{suffix}"


def build_overview_rich(app, p: str) -> str:
    builtins, installed = [], []
    for item in sorted(app.modules.values(), key=lambda m: m.name.casefold()):
        if item.name in app.loader.sources:
            installed.append(item)
        else:
            builtins.append(item)

    disabled = app.kv.ns("core").get("disabled_modules", [])
    total = len(app.modules)
    hidden_part = f", {len(disabled)} выключено" if disabled else ""

    def make_table(items):
        if not items:
            return "<p><i>Модулей пока нет.</i></p>"
        rows = ["<tr><th>Модуль</th><th>Команды</th></tr>"]
        for item in items:
            mod_cell = f"<td>{{e:bullet_circle}} <code>{html.escape(item.name)}</code></td>"
            if item.commands:
                cmds = ", ".join(f"<code>{html.escape(c.name)}</code>" for c in item.commands)
                cmd_cell = f"<td>{cmds}</td>"
            else:
                cmd_cell = "<td><i>работает в фоне</i></td>"
            rows.append(f"<tr>{mod_cell}{cmd_cell}</tr>")
        return f'<table bordered striped compact>{"".join(rows)}</table>'

    builtin_table = make_table(builtins)
    installed_table = make_table(installed)

    lines = [
        "<h1>{e:logo} Список модулей</h1>",
        f"<p><b>{total} модулей доступно{hidden_part}:</b></p>",
        f"<details><summary>Встроенные модули</summary>{builtin_table}</details>",
        f"<details><summary>Дополнительные модули</summary>{installed_table}</details>",
    ]
    return "\n".join(lines)


def build_detail_rich(item, p: str) -> str:
    lines = [f"<h1>{{e:module}} <code>{html.escape(item.name)}</code> · {html.escape(item.version)}</h1>"]
    if item.author:
        lines.append(f"<p>Автор: <b>{html.escape(item.author)}</b></p>")
    if item.commands:
        rows = ["<tr><th>Команда</th><th>Описание</th></tr>"]
        for c in item.commands:
            aliases = ", ".join(p + name for name in c.aliases)
            alias_suffix = f" <small>({html.escape(aliases)})</small>" if aliases else ""
            rows.append(f"<tr><td><code>{p}{html.escape(c.name)}</code>{alias_suffix}</td>"
                        f"<td>{html.escape(explain(c))}</td></tr>")
        lines.append(f'<table bordered striped compact>{"".join(rows)}</table>')
    else:
        lines.append("<p><i>Работает в фоне, без команд.</i></p>")

    notes = []
    descriptions = " ".join(explain(c) for c in item.commands)
    if "<" in descriptions or "[" in descriptions or "&lt;" in descriptions:
        notes.append("Вместо &lt;…&gt; подставь свой текст; […] — необязательная часть.")
    if item.listens_all:
        notes.append("{e:warn} Слушает все сообщения — без ограничения области работы.")
    if notes:
        lines.append(f"<footer>{'<br>'.join(notes)}</footer>")
    return "\n".join(lines)


@module.command("help", aliases=("h",))
async def help_command(client: Client, message: Message):
    # — справка; пример: .help Ping
    query = raw_args(message).strip()
    app, p = module.app, module.app.router.prefixes[0]
    if not query:
        commands = []
        for item in app.modules.values():
            if item.commands:
                names = "  ".join(html.code(p + command.name) for command in item.commands)
                commands.append(f"<b>{html.escape(item.name)}</b>\n{names}")
        listing = "\n\n".join(commands)
        text = (
            f"{module.t('intro', p=p)}\n\n"
            f"<blockquote>{listing}</blockquote>"
        )
        rich = build_overview_rich(app, p)
        return await respond(message, text, rich_text=rich, banner=module.config["banner"])

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

    rich = build_detail_rich(item, p)
    await respond(message, "\n\n".join(lines), rich_text=rich, banner=item.banner)
