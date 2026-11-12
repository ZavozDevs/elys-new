import inspect

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, UserError, html, raw_args, respond

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
    version = f" · {html.escape(item.version)}" if item.version else ""
    lines = [f"<h1>{{e:module}} <code>{html.escape(item.name)}</code>{version}</h1>"]
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
        return await respond(message, rich_text=build_overview_rich(app, p), banner=module.config["banner"])

    item = app.loader.resolve(query)
    command = app.router.get(query.removeprefix(p))
    if item is None and command is not None:
        item = command.owner
    if item is None:
        raise UserError(module.t("not_found"))
    await respond(message, rich_text=build_detail_rich(item, p), banner=item.banner)
