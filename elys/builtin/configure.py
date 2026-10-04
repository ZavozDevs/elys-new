from __future__ import annotations

import json
import secrets
import string
from contextlib import suppress

from pyrogram import Client
from pyrogram.types import Message

from elys import Button, Config, E, Module, UserError, html, raw_args, respond

module = Module("Configure")
_TOKENS = string.ascii_letters + string.digits
_input_tokens: dict[str, tuple[str, str, str]] = {}
CORE_NAMES = {
    "prefixes": "Начало команды", "language": "Язык", "banners": "Картинки над ответами",
    "aliases": "Сокращения", "start_banner": "Картинка приветствия",
}


def make_token_btn(text: str, action: str, mod: str, key: str, **kwargs) -> Button:
    if len(_input_tokens) > 200:
        for old in list(_input_tokens)[:50]:
            _input_tokens.pop(old, None)
    token = "".join(secrets.choice(_TOKENS) for _ in range(5))
    _input_tokens[token] = (action, mod, key)
    return Button(text, query=f"cfg {token} ", **kwargs)


def apply_core(app, key, value):
    core = app.kv.ns("core")
    if key == "prefixes":
        prefixes = value.split() if isinstance(value, str) else list(value)
        if not prefixes:
            raise ValueError("Напиши хотя бы один знак, например . или !")
        app.router.prefixes = prefixes
        core[key] = list(app.router.prefixes)
    elif key == "language":
        if value not in {"ru", "en"}:
            raise ValueError("Выбери русский или английский язык кнопкой")
        app.language = core[key] = value
    elif key == "banners":
        if isinstance(value, str):
            value = value.lower() in {"1", "true", "on", "yes", "вкл", "включено"}
        if type(value) is not bool:
            raise ValueError("Выбери включение или выключение кнопкой")
        app.banners_enabled = core[key] = value
    elif key == "start_banner":
        core[key] = Config.url().validate(value.strip())
    elif key == "aliases":
        parts = value.lower().split()
        if len(parts) != 2:
            raise ValueError("Напиши сокращение и команду без точки, например: п ping")
        name, target_cmd = parts
        command = app.router.get(target_cmd)
        if command is None:
            raise ValueError("Такой команды нет. Посмотри список команд через help")
        app.router.set_aliases({**app.router.aliases, name: command.name})
        core[key] = app.router.aliases
    else:
        raise ValueError("Неизвестная настройка")


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
            raise ValueError("Нужно целое число, например 10") from None
    elif kind is float:
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            raise ValueError("Нужно число, например 1.5") from None
    else:
        try:
            value = json.loads(text)
        except ValueError:
            raise ValueError('Нужна запись JSON, например ["первый", "второй"] для списка') from None
    return field.validate(value)


def shown(value, *, secret=False):
    if secret:
        return "•••• · скрыто" if value else "не задано"
    if value == "":
        return "не задано"
    if type(value) is bool:
        return "включено" if value else "выключено"
    return html.code(str(value)[:300])


def go(text, route, **kwargs):
    return Button(text, navigate, route, **kwargs)


def back(route):
    return [go("‹ Назад", route)]


def paged(rows, route, page=0, per_page=6, cols=2):
    flat = [b for item in rows for b in (item if isinstance(item, list) else [item])]
    count = max(1, (len(flat) + per_page - 1) // per_page)
    page = min(max(page, 0), count - 1)
    slice_ = flat[page * per_page : (page + 1) * per_page]
    result = [slice_[i : i + cols] for i in range(0, len(slice_), cols)]
    nav = []
    if page:
        nav.append(go("‹ Предыдущие", (*route, page - 1)))
    if page + 1 < count:
        nav.append(go("Следующие ›", (*route, page + 1)))
    if nav:
        result.append(nav)
    return result


def target(name):
    item = module.app.modules.get(name)
    if item is None or not item.loaded:
        raise ValueError("Модуль уже выключен. Вернись к списку модулей.")
    return item


def screen(route):
    app = module.app
    kind, *args = route
    p = app.router.prefixes[0]
    if kind == "home":
        return (f"{E.gear} <b>Elys · настройки</b>\n\n"
                "<blockquote>Выбери раздел настроек.</blockquote>\n\n"
                f"Открыть снова → {html.code(p + 'config')}",
                [[go("Настройки Elys", ("core",), style="primary", icon="gear"),
                  go("Настройки модулей", ("modules", 0), icon="folder")],
                 [Button("Закрыть", close, icon="cross")]])
    if kind == "core":
        aliases = len(app.router.aliases)
        text = (f"{E.gear} <b>Настройки Elys</b>\n\n<blockquote>"
                f"Префиксы: {html.code(' '.join(app.router.prefixes))}\n"
                f"Язык: {'Русский' if app.language == 'ru' else 'English'}\n"
                f"Картинки: {'вкл' if app.banners_enabled else 'выкл'}\n"
                f"Сокращений: {aliases}</blockquote>")
        items = [go(name, ("core_field", key)) for key, name in CORE_NAMES.items()]
        rows = [items[i : i + 2] for i in range(0, len(items), 2)]
        return text, [*rows, back(("home",))]
    if kind == "core_field":
        key = args[0]
        text = f"{E.gear} <b>{CORE_NAMES[key]}</b>\n\n"
        if key == "prefixes":
            text += (f"Сейчас: {html.code(' '.join(app.router.prefixes))}\n"
                     "Знак перед командой (например <code>. !</code>).")
            rows = [[make_token_btn("Изменить", "core", "core", "prefixes", style="primary", icon="memo")]]
        elif key == "start_banner":
            text += (f"Сейчас: {shown(app.kv.ns('core').get('start_banner', ''))}\n"
                     "Ссылка на картинку приветствия форума.")
            rows = [[make_token_btn("Задать ссылку", "core", "core", "start_banner", style="primary"),
                     Button("Убрать картинку", set_core, (key, ""))]]
        elif key == "language":
            text += "Язык интерфейса бота."
            rows = [[Button(("✓ " if app.language == code else "") + name, set_core, (key, code))
                     for code, name in (("ru", "Русский"), ("en", "English"))]]
        elif key == "banners":
            text += f"Сейчас: {shown(app.banners_enabled)}.\nПоказ картинок над ответами команд."
            rows = [[Button("Выключить" if app.banners_enabled else "Включить", set_core,
                            (key, not app.banners_enabled), style="primary")]]
        else:
            text += "Второе имя команды, например <code>п</code> → <code>ping</code>."
            items = [Button(f"Удалить: {name} → {cmd}", remove_alias, name) for name, cmd in app.router.aliases.items()]
            rows = paged(items, ("core_field", "aliases"), args[1] if len(args) > 1 else 0, cols=1)
            rows.append([make_token_btn("Добавить сокращение", "core", "core", "aliases", style="primary")])
        return text, [*rows, back(("core",))]
    if kind == "modules":
        items = sorted((m for m in app.modules.values() if m.config), key=lambda m: m.name.casefold())
        btns = [go(item.name, ("module", item.name, 0)) for item in items]
        return (f"{E.gear} <b>Настройки модулей</b>\n\nВыбери модуль:",
                [*paged(btns, ("modules",), args[0]), back(("home",))])
    item = target(args[0])
    if kind == "module":
        btns = [go(field.doc[:45] or key, ("field", item.name, key, 0)) for key, field in item.config.fields.items()]
        return (f"{E.gear} <b>{html.escape(item.name)} · настройки</b>\n\nВыбери параметр:",
                [*paged(btns, ("module", item.name), args[1]), back(("modules", 0))])
    key = args[1]
    field = item.config.fields[key]
    route = ("field", item.name, key, 0)
    title = f"{E.gear} <b>{html.escape(item.name)} · {html.escape(key)}</b>\n\n"
    if kind == "reset":
        text = title + f"Вернуть значение по умолчанию: {shown(field.default, secret=field.secret)}?"
        reset_button = Button("Вернуть по умолчанию", reset, (item.name, key), style="danger", icon="recycle")
        return text, [[reset_button], back(route)]
    text = (title + html.escape(field.doc) + "\n\n<blockquote>"
            f"Сейчас: {shown(item.config[key], secret=field.secret)}\n"
            f"По умолчанию: {shown(field.default, secret=field.secret)}</blockquote>")
    if field.choices:
        btns = [Button(f"Вариант {i + 1}" if field.secret else str(v)[:50], set_field, (item.name, key, v))
                for i, v in enumerate(field.choices)]
        rows = paged(btns, ("field", item.name, key), args[2])
    elif type(field.default) is bool:
        rows = [[Button("Выключить" if item.config[key] else "Включить", set_field,
                        (item.name, key, not item.config[key]), style="primary")]]
    elif isinstance(field.default, (int, float)) and type(field.default) is not bool:
        rows = [
            [Button("-10", step_field, (item.name, key, -10)),
             Button("-1", step_field, (item.name, key, -1)),
             Button("+1", step_field, (item.name, key, 1)),
             Button("+10", step_field, (item.name, key, 10))],
            [make_token_btn("Ввести число", "set", item.name, key, style="primary", icon="memo")],
        ]
    elif isinstance(field.default, list):
        item_btns = [Button(f"❌ {str(v)[:25]}", remove_item, (item.name, key, v)) for v in item.config[key]]
        rows = paged(item_btns, ("field", item.name, key), args[2])
        action_row = [make_token_btn("➕ Добавить", "add", item.name, key, style="primary")]
        if item.config[key]:
            action_row.append(Button("Очистить", set_field, (item.name, key, [])))
        rows.append(action_row)
    else:
        action_row = [make_token_btn("Изменить", "set", item.name, key, style="primary", icon="memo")]
        if type(field.default) is str and item.config[key]:
            action_row.append(Button("Очистить", set_field, (item.name, key, "")))
        rows = [action_row]
    nav = []
    if item.config[key] != field.default:
        nav.append(go("Вернуть по умолчанию", ("reset", item.name, key)))
    nav.extend(back(("module", item.name, 0)))
    rows.append(nav)
    return text, rows


async def show(query, route):
    try:
        text, rows = screen(route)
    except (ValueError, KeyError):
        await query.answer("Этой настройки больше нет. Вернись к списку модулей.", show_alert=True)
        text, rows = screen(("modules", 0))
    await module.app.inline.edit(query, text, rows)


async def navigate(bot, query, route):
    await show(query, route)


async def close(bot, query, data):
    unit = module.app.inline.from_query(query)
    text = f"Настройки закрыты. Открыть снова → {html.code(module.app.router.prefixes[0] + 'config')}"
    await module.app.inline.edit(query, text)
    if unit:
        module.app.inline.units.remove(unit.id)


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


@module.command("config")
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
                raise UserError("У этого модуля нет настроек. Напиши config с твоим префиксом — покажу список.")
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
                raise UserError(f"Неизвестная настройка core: {key}. Доступны: {', '.join(CORE_NAMES)}")
            route = ("core_field", key)
        else:
            item = module.app.loader.resolve(target_name)
            if item is None or not item.config:
                raise UserError(f"У модуля {target_name} нет настроек.")
            if key not in item.config.fields:
                raise UserError(f"У модуля {item.name} нет настройки {key}. Доступны: {', '.join(item.config.fields)}")
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
            raise UserError(f"Неизвестная настройка core: {key}. Доступны: {', '.join(CORE_NAMES)}")
        try:
            apply_core(app, key, val)
        except ValueError as exc:
            raise UserError(str(exc)) from None
        await respond(message, f"{E.check} <b>Elys · {CORE_NAMES[key]}</b> обновлено: <code>{html.escape(val)}</code>")
        return

    item = app.loader.resolve(target_name)
    if item is None or not item.config:
        raise UserError(f"У модуля {target_name} нет настроек.")
    if key not in item.config.fields:
        raise UserError(f"У модуля {item.name} нет настройки {key}. Доступны: {', '.join(item.config.fields)}")

    field = item.config.fields[key]
    try:
        item.config[key] = parse_value(field, val)
    except (ValueError, TypeError) as exc:
        raise UserError(f"Не удалось применить настройку: {exc}") from None

    shown_val = "••••" if field.secret else str(item.config[key])
    await respond(message, f"{E.check} <b>{item.name} · {key}</b> обновлено: <code>{html.escape(shown_val)}</code>")


@module.callback("elys:settings")
async def from_welcome(bot, query):
    text, rows = screen(("home",))
    await module.app.inline.bot_form(module, query.message.chat.id, text, rows)
    await query.answer()


@module.loop(1800)
async def refresh_premium(client: Client):
    module.app.premium = bool((await client.get_me()).is_premium)


@module.on_ready
async def ready(client: Client):
    refresh_premium.start()


@module.on_unload
async def unload(client: Client):
    pass
