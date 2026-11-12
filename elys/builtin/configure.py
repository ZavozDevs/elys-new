from __future__ import annotations

import json
from contextlib import suppress

from pyrogram import Client
from pyrogram.errors import RPCError
from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent, Message

from elys import Button, Config, Module, UserError, html, raw_args, respond
from elys.builtin.welcome import START_BANNER
from elys.inline.list import nav_row

module = Module("Configure")
t = module.t
CORE_NAMES = ("prefixes", "language", "banners", "rich", "aliases", "start_banner")  # подпись — t(f"name.{key}")
RICH_MODES = ("auto", "bot", "off")


def input_btn(text: str, action: str, name: str, key: str, **kwargs) -> Button:
    # ввод значения: «@бот cfg <форма>:<кнопка> значение»; что меняем — в data самой кнопки
    return Button(text, query="cfg {button} ", data=(action, name, key), **kwargs)


def languages(app) -> dict[str, dict]:
    catalog = getattr(app, "i18n", None)
    return (
        catalog.languages()
        if catalog is not None
        else {"ru": {"name": "Русский", "flag": ""}, "en": {"name": "English", "flag": ""}}
    )


def language_name(app, code: str) -> str:
    meta = languages(app).get(code, {"name": code, "flag": ""})
    return f"{meta['flag']} {meta['name']}".strip()


def apply_core(app, key, value):
    core = app.kv.ns("core")
    if key == "prefixes":
        prefixes = value.split() if isinstance(value, str) else list(value)
        if not prefixes:
            raise ValueError(t("err.prefixes"))
        app.router.prefixes = prefixes
        core[key] = list(app.router.prefixes)
    elif key == "language":
        if value not in languages(app):
            raise ValueError(t("err.language"))
        app.language = core[key] = value
    elif key == "banners":
        if isinstance(value, str):
            value = value.lower() in {"1", "true", "on", "yes", "вкл", "включено"}
        if type(value) is not bool:
            raise ValueError(t("err.banners"))
        app.banners_enabled = core[key] = value
    elif key == "rich":
        if value not in RICH_MODES:
            raise ValueError(t("err.rich"))
        app.rich = core[key] = value
    elif key == "start_banner":
        core[key] = Config.url().validate(value.strip())
    elif key == "aliases":
        parts = value.lower().split()
        if len(parts) != 2:
            raise ValueError(t("err.aliases"))
        name, target_cmd = parts
        command = app.router.get(target_cmd)
        if command is None:
            raise ValueError(t("err.command"))
        app.router.set_aliases({**app.router.aliases, name: command.name})
        core[key] = app.router.aliases
    else:
        raise ValueError(t("err.unknown"))


def parse_item(field, text):
    item_type = getattr(field, "item_type", None)
    if item_type is int:
        return int(text)
    if item_type is float:
        return float(text.replace(",", "."))
    return text.strip()


def parse_value(field, text):
    kind = type(field.default)
    if kind is str:
        value = text
    elif kind is int:
        try:
            value = int(text)
        except ValueError:
            raise ValueError(t("err.int")) from None
    elif kind is float:
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            raise ValueError(t("err.float")) from None
    else:
        try:
            value = json.loads(text)
        except ValueError:
            raise ValueError(t("err.json")) from None
    return field.validate(value)


def shown(value, *, secret=False):
    if secret:
        return t("hidden" if value else "unset")
    if value == "":
        return t("unset")
    if type(value) is bool:
        return t("on" if value else "off")
    return html.code(str(value)[:300])


def label(item, key):
    # подпись настройки: cfg.<ключ> из пака модуля, иначе doc из Config
    return item.t(f"cfg.{key}", default=item.config.fields[key].doc or key)


def field_name(name, key):
    return f"Elys › {t(f'name.{key}')}" if name == "core" else f"{name} › {label(target(name), key)}"


def go(text, route, **kwargs):
    return Button(text, navigate, route, **kwargs)


def back(route):
    return [go(t("back"), route, style="primary")]


def is_system(item):
    # встроенный модуль — тот, что не установлен из файла пользователя.
    return item.name not in module.app.loader.sources


def paged(rows, route, page=0, per_page=6, cols=2):
    flat = [b for item in rows for b in (item if isinstance(item, list) else [item])]
    count = max(1, (len(flat) + per_page - 1) // per_page)
    page = min(max(page, 0), count - 1)
    slice_ = flat[page * per_page : (page + 1) * per_page]
    result = [slice_[i : i + cols] for i in range(0, len(slice_), cols)]
    result += nav_row(page, count, lambda text, index, style: go(text, (*route, index), style=style))
    return result


def scope_of(item):
    return "system" if is_system(item) else "user"


def target(name):
    item = module.app.modules.get(name)
    if item is None or not item.loaded:
        raise ValueError(t("gone_module"))
    return item


def screen(route):
    app = module.app
    kind, *args = route
    if kind == "home":
        count = {s: sum(bool(m.config) and scope_of(m) == s for m in app.modules.values()) for s in ("system", "user")}
        return (
            t("home"),
            [
                [go(t("core"), ("core",), style="primary", icon="gear")],
                [go(t(s, n=count[s]), ("modules", s, 0), icon="modules") for s in ("system", "user")],
                [Button(t("close"), close, style="danger", icon="cross")],
            ],
        )
    if kind == "core":
        items = [go(t(f"name.{key}"), ("core_field", key)) for key in CORE_NAMES]
        return t("core_text"), [*(items[i : i + 2] for i in range(0, len(items), 2)), back(("home",))]
    if kind == "core_field":
        key = args[0]
        now = ""
        if key == "prefixes":
            now = html.code(" ".join(app.router.prefixes))
            rows = [[input_btn(t("change"), "core", "core", "prefixes", style="primary")]]
        elif key == "start_banner":
            now = shown(app.kv.ns("core").get("start_banner", START_BANNER))
            rows = [
                [
                    input_btn(t("set_link"), "core", "core", "start_banner", style="primary"),
                    Button(t("remove_banner"), set_core, (key, "")),
                ]
            ]
        elif key == "language":
            now = language_name(app, app.language)
            items = [
                Button(
                    language_name(app, code),
                    set_core,
                    (key, code),
                    style="success" if app.language == code else "default",
                )
                for code in languages(app)
            ]
            rows = [items[i : i + 2] for i in range(0, len(items), 2)]
        elif key == "banners":
            now = shown(app.banners_enabled)
            rows = [
                [
                    Button(t(s), set_core, (key, v), style="success" if app.banners_enabled == v else "default")
                    for s, v in (("btn_on", True), ("btn_off", False))
                ]
            ]
        elif key == "rich":
            now = t(f"rich.{app.rich}")
            rows = [
                [
                    Button(t(f"rich.{m}"), set_core, (key, m), style="success" if app.rich == m else "default")
                    for m in RICH_MODES
                ]
            ]
        else:
            items = [
                Button(t("remove_alias", name=name, command=cmd), remove_alias, name)
                for name, cmd in app.router.aliases.items()
            ]
            rows = paged(items, ("core_field", "aliases"), args[1] if len(args) > 1 else 0, cols=1)
            rows.append([input_btn(t("add_alias"), "core", "core", "aliases", style="primary")])
        text = (
            t("field_title", name=field_name("core", key))
            + (t("now", value=now) + "\n\n" if now else "")
            + f"<blockquote expandable>{t(f'{key}_hint')}</blockquote>\n\n"
            + t("usage", module="core", field=key)
        )
        return text, [*rows, back(("core",))]
    if kind == "modules":
        scope = args[0]
        if scope not in ("system", "user"):
            raise ValueError("неизвестный раздел модулей")
        items = sorted(
            (m for m in app.modules.values() if m.config and is_system(m) == (scope == "system")),
            key=lambda m: m.name.casefold(),
        )
        btns = [go(item.name, ("module", item.name, 0)) for item in items]
        return (
            t(f"{scope}_title") + ("" if items else "\n\n" + t("no_modules")),
            [*paged(btns, ("modules", scope), args[1]), back(("home",))],
        )
    item = target(args[0])
    if kind == "module":
        about = item.t("about", default="")
        # • — значение изменено; True * " •" == " •"
        btns = [
            go(label(item, key)[:45] + " •" * (item.config[key] != field.default), ("field", item.name, key, 0))
            for key, field in item.config.fields.items()
        ]
        return (
            t("module_title", name=item.name, about=html.Html(f"\n<i>{about}</i>" if about else "")),
            [*paged(btns, ("module", item.name), args[1]), back(("modules", scope_of(item), 0))],
        )
    key = args[1]
    field = item.config.fields[key]
    route = ("field", item.name, key, 0)
    title = t("field_title", name=field_name(item.name, key))
    if kind == "reset":
        return (
            title + t("reset_question", value=shown(field.default, secret=field.secret)),
            [[Button(t("reset"), reset, (item.name, key), style="danger"), go(t("cancel"), route)]],
        )
    # необязательные ключи пака модуля: подсказка и подпись пустого значения
    hint, empty = (item.t(f"cfg.{key}.{part}", default="") for part in ("hint", "empty"))
    text = (
        title
        + t(
            "values",
            current=(item.config[key] == "" and empty) or shown(item.config[key], secret=field.secret),
            initial=(field.default == "" and empty) or shown(field.default, secret=field.secret),
        )
        + (f"\n\n<blockquote expandable>{hint}</blockquote>" if hint else "")
        + "\n\n"
        + t("usage", module=item.name, field=key)
    )
    if field.choices:
        btns = [
            Button(
                t("choice", n=i + 1) if field.secret else str(v)[:50],
                set_field,
                (item.name, key, v),
                style="success" if item.config[key] == v else "default",
            )
            for i, v in enumerate(field.choices)
        ]
        rows = paged(btns, ("field", item.name, key), args[2])
    elif type(field.default) is bool:
        rows = [
            [
                Button(t(s), set_field, (item.name, key, v), style="success" if item.config[key] == v else "default")
                for s, v in (("btn_on", True), ("btn_off", False))
            ]
        ]
    elif isinstance(field.default, (int, float)):
        rows = [
            [Button(f"{n:+}", step_field, (item.name, key, n)) for n in (-10, -1, 1, 10)],
            [input_btn(t("enter_number"), "set", item.name, key, style="primary")],
        ]
    elif isinstance(field.default, list):
        item_btns = [Button(str(v)[:25], remove_item, (item.name, key, v), style="danger") for v in item.config[key]]
        rows = paged(item_btns, ("field", item.name, key), args[2])
        rows.append(
            [input_btn(t("add"), "add", item.name, key, style="primary")]
            + [Button(t("clear"), set_field, (item.name, key, []))] * bool(item.config[key])
        )
    else:
        clearable = type(field.default) is str and bool(item.config[key])
        rows = [
            [input_btn(t("change"), "set", item.name, key, style="primary")]
            + [Button(t("clear"), set_field, (item.name, key, ""))] * clearable
        ]
    if item.config[key] != field.default:
        rows.append([go(t("reset"), ("reset", item.name, key), style="danger")])
    return text, [*rows, back(("module", item.name, 0))]


async def show(query, route):
    try:
        text, rows = screen(route)
    except (ValueError, KeyError):
        await query.answer(t("gone"), show_alert=True)
        text, rows = screen(("home",))
    await module.app.inline.edit(query, text, rows)


async def navigate(bot, query, route):
    await show(query, route)


async def close(bot, query, data):
    await module.app.inline._dismiss(bot, query, data)


async def set_core(bot, query, data):
    key, value = data
    apply_core(module.app, key, value)
    await show(query, ("core_field", key))


async def remove_alias(bot, query, name):
    app = module.app
    app.router.set_aliases({k: v for k, v in app.router.aliases.items() if k != name})
    app.kv.ns("core")["aliases"] = app.router.aliases
    await show(query, ("core_field", "aliases"))


async def set_field(bot, query, data):
    name, key, value = data
    try:
        target(name).config[key] = value
    except (ValueError, KeyError) as exc:
        await query.answer(str(exc)[:180], show_alert=True)
        return
    await show(query, ("field", name, key, 0))


async def reset(bot, query, data):
    name, key = data
    del target(name).config[key]
    await show(query, ("field", name, key, 0))


async def step_field(bot, query, data):
    name, key, delta = data
    item = target(name)
    val = item.config[key] + delta
    field = item.config.fields[key]
    if field.min is not None and val < field.min:
        val = field.min
    if field.max is not None and val > field.max:
        val = field.max
    try:
        item.config[key] = val
    except ValueError as exc:
        await query.answer(str(exc)[:180], show_alert=True)
        return
    await show(query, ("field", name, key, 0))


async def remove_item(bot, query, data):
    name, key, val = data
    item = target(name)
    current = list(item.config[key])
    if val in current:
        current.remove(val)
        item.config[key] = current
    await show(query, ("field", name, key, 0))


def pressed(query):
    # «cfg <форма>:<кнопка> значение» → форма, (действие, модуль, ключ) с кнопки, значение
    ref, _, value = query.removeprefix("cfg ").partition(" ")
    unit_id, _, index = ref.partition(":")
    unit = module.app.inline.units.get(unit_id)
    button = unit.buttons.get(int(index)) if unit and index.isdigit() else None
    return unit, getattr(button, "data", None), value.strip()


def apply(action, name, key, value):
    if name == "core":
        return apply_core(module.app, key, value)
    item = target(name)
    field = item.config.fields[key]
    item.config[key] = [*item.config[key], parse_item(field, value)] if action == "add" else parse_value(field, value)


@module.inline("cfg ")
async def input_hint(bot, query):
    _, data, value = pressed(query.query)
    results = []
    if data:
        title = t("input.add" if data[0] == "add" else "input.save", value=value) if value else t("input.empty")
        results.append(
            InlineQueryResultArticle(title, InputTextMessageContent("⏳"), id="cfg", description=field_name(*data[1:]))
        )
    await query.answer(results, cache_time=0, is_personal=True)


@module.chosen("cfg ")
async def input_value(bot, result):
    unit, data, value = pressed(result.query)
    if not data:
        return
    action, name, key = data
    note = ""
    if value:
        try:
            apply(action, name, key, value)
        except (ValueError, TypeError, KeyError) as exc:
            note = t("bad_value", error=str(exc))
    text, rows = screen(("core_field", key) if name == "core" else ("field", name, key, 0))
    await module.app.inline.edit(unit, note + text, rows)
    await drop_input(unit)


async def drop_input(unit):
    # «⏳» ушёл от владельца через бота в чат формы — убираем его. Ищем по автору и боту, не по out:
    # в «Избранном» у своих сообщений out=False.
    me, bot_id, chat = module.client.me.id, module.app.bot.me.id, unit.data.get("chat_id")
    if unit.data.get("direct") and chat == me:
        chat = bot_id  # личка с ботом глазами юзербота
    with suppress(RPCError):
        async for message in module.client.get_chat_history(chat, limit=5):
            if getattr(message.via_bot, "id", None) == bot_id and getattr(message.from_user, "id", None) == me:
                return await message.delete()
    module.log.warning("не нашёл «⏳» в чате %s", chat)


@module.command("config", roles=("sudo",))
async def configure(client: Client, message: Message):
    # — настройки Elys и модулей: меню с кнопками или быстрый ввод .config <модуль> [ключ] [значение]
    query = raw_args(message).strip()
    if not query:
        text, rows = screen(("home",))
        await module.form(message, text, rows)
        with suppress(Exception):
            await message.delete()
        return

    parts = query.split(None, 2)
    target_name = parts[0]

    if len(parts) == 1:
        if target_name.lower() == "core":
            route = ("core",)
        else:
            item = module.app.loader.resolve(target_name)
            if item is None or not item.config:
                raise UserError(t("no_config"))
            route = ("module", item.name, 0)
        text, rows = screen(route)
        await module.form(message, text, rows)
        with suppress(Exception):
            await message.delete()
        return

    if len(parts) == 2:
        key = parts[1]
        if target_name.lower() == "core":
            if key not in CORE_NAMES:
                raise UserError(t("unknown_core", key=key, keys=", ".join(CORE_NAMES)))
            route = ("core_field", key)
        else:
            item = module.app.loader.resolve(target_name)
            if item is None or not item.config:
                raise UserError(t("module_no_config", name=target_name))
            if key not in item.config.fields:
                raise UserError(t("no_field", name=item.name, key=key, keys=", ".join(item.config.fields)))
            route = ("field", item.name, key, 0)
        text, rows = screen(route)
        await module.form(message, text, rows)
        with suppress(Exception):
            await message.delete()
        return

    key, val = parts[1], parts[2]
    app = module.app
    if target_name.lower() == "core":
        if key not in CORE_NAMES:
            raise UserError(t("unknown_core", key=key, keys=", ".join(CORE_NAMES)))
        try:
            apply_core(app, key, val)
        except ValueError as exc:
            raise UserError(str(exc)) from None
        await respond(message, t("updated", name=field_name("core", key), value=val))
        return

    item = app.loader.resolve(target_name)
    if item is None or not item.config:
        raise UserError(t("module_no_config", name=target_name))
    if key not in item.config.fields:
        raise UserError(t("no_field", name=item.name, key=key, keys=", ".join(item.config.fields)))

    field = item.config.fields[key]
    try:
        item.config[key] = parse_value(field, val)
    except (ValueError, TypeError) as exc:
        raise UserError(t("apply_failed", error=exc)) from None

    shown_val = "••••" if field.secret else str(item.config[key])
    await respond(message, t("updated", name=field_name(item.name, key), value=shown_val))


@module.callback("elys:settings")
async def from_welcome(bot, query):
    text, rows = screen(("home",))
    await module.app.inline.bot_form(module, query.message.chat.id, text, rows)
    await query.answer()


@module.on_unload
async def unload(client: Client):
    pass
