import inspect

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, E, Module, UserError, html, raw_args, respond

BANNER = "https://raw.githubusercontent.com/ZavozDevs/assets/main/elys_userbot/cmd.png"

module = Module("Help", config=Config(banner=Config.url(BANNER, doc="Баннер")))


def explain(command):
    doc = command.callback.__doc__
    if not doc:
        try:
            # в builtin описание — первый комментарий, в сторонних модулях — docstring.
            doc = next(
                (
                    line.strip()[1:].strip()
                    for line in inspect.getsource(command.callback).splitlines()
                    if line.strip().startswith("#")
                ),
                "",
            )
        except (OSError, TypeError):
            doc = ""
    return (doc or module.t("no_doc")).strip().splitlines()[0].lstrip("— ")


def describe(command, prefix):
    doc = explain(command)
    aliases = ", ".join(prefix + name for name in command.aliases)
    suffix = f" ({html.escape(aliases)})" if aliases else ""
    return f"{html.code(prefix + command.name)} — {html.escape(doc)}{suffix}"


def build_overview_rich(app, p: str) -> str:
    t, sources = module.t, app.loader.sources
    items = sorted(app.modules.values(), key=lambda m: m.name.casefold())

    def table(group):
        rows = "".join(
            f"<tr><td>{{e:bullet_circle}} <code>{html.escape(m.name)}</code></td><td>"
            + (
                ", ".join(f"<code>{html.escape(c.name)}</code>" for c in m.commands)
                or f"<i>{t('background_short')}</i>"
            )
            + "</td></tr>"
            for m in group
        )
        head = f"<tr><th>{t('module')}</th><th>{t('commands')}</th></tr>"
        return f"<table bordered striped compact>{head}{rows}</table>" if rows else f"<p><i>{t('empty')}</i></p>"

    disabled = app.kv.ns("core").get("disabled_modules", [])
    total = t("total", n=len(app.modules)) + (t("disabled", n=len(disabled)) if disabled else "")
    return "\n".join(
        [
            f"<h1>{{e:modules}} {t('modules')}</h1>",
            f"<p><b>{total}</b></p>",
            f"<details><summary>{t('builtin')}</summary>{table([m for m in items if m.name not in sources])}</details>",
            f"<details><summary>{t('installed')}</summary>{table([m for m in items if m.name in sources])}</details>",
        ]
    )


def build_detail_rich(item, p: str) -> str:
    t = module.t
    lines = [f"<h1>{{e:module}} <code>{html.escape(item.name)}</code> · {html.escape(item.version)}</h1>"]
    if item.author:
        lines.append(f"<p>{t('author', author=html.b(item.author))}</p>")
    if item.commands:
        rows = [f"<tr><th>{t('command')}</th><th>{t('description')}</th></tr>"]
        for c in item.commands:
            aliases = ", ".join(p + name for name in c.aliases)
            alias_suffix = f" <small>({html.escape(aliases)})</small>" if aliases else ""
            rows.append(
                f"<tr><td><code>{p}{html.escape(c.name)}</code>{alias_suffix}</td>"
                f"<td>{html.escape(explain(c))}</td></tr>"
            )
        lines.append(f"<table bordered striped compact>{''.join(rows)}</table>")
    else:
        lines.append(f"<p><i>{t('background')}</i></p>")
    descriptions = " ".join(explain(c) for c in item.commands)
    # [x] * bool — заметка попадает в список только при условии, без ветвлений
    notes = [t("arguments")] * any(mark in descriptions for mark in ("<", "[", "&lt;")) + [t("listens_all")] * bool(
        item.listens_all
    )
    if notes:
        lines.append(f"<footer>{'<br>'.join(notes)}</footer>")
    return "\n".join(lines)


@module.command("help", aliases=("h",), roles=("sudo", "support"))
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
        text = f"{module.t('intro')}\n\n<blockquote>{listing}</blockquote>"
        rich = build_overview_rich(app, p)
        return await respond(message, text, rich_text=rich, banner=module.config["banner"])

    item = app.loader.resolve(query)
    command = app.router.get(query.removeprefix(p))
    if item is None and command is not None:
        item = command.owner
    if item is None:
        raise UserError(module.t("not_found"))

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
