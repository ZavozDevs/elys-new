from pyrogram import Client
from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from elys import Module, html

module = Module("Welcome")

@module.on_ready
async def greet(client: Client) -> None:
    app = module.app
    forum = getattr(app, "forum", None)
    if forum is None:
        return
    if forum.state.get("welcome"):
        return
    p = app.router.prefixes[0]
    text = ("🌟 <b>Elys работает!</b>\n\n"
            "Команда — обычное сообщение со знаком в начале. Напиши " + html.code(p + "ping") +
            " — проверить связь.\n\n<blockquote>"
            + html.code(p + "help") + " — список команд\n" + html.code(p + "config") + " — настройки</blockquote>\n\n"
            "Команды выполняются только из твоих сообщений. Собеседники не могут управлять Elys.\n"
            "Ответы и меню видны участникам чата. Для личных команд используй этот чат.")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Список команд", callback_data="elys:commands", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("Настройки", callback_data="elys:settings", style=ButtonStyle.SUCCESS)],
    ])
    banner = app.kv.ns("core").get("start_banner")
    if banner:
        message = await app.bot.send_photo(forum.chat_id, banner, caption=text, reply_markup=markup)
    else:
        message = await app.bot.send_message(forum.chat_id, text, reply_markup=markup)
    await app.bot.pin_chat_message(forum.chat_id, message.id, disable_notification=True)
    forum.state["welcome"] = message.id
    await forum._save()


@module.callback("elys:commands")
async def commands(bot, query):
    app, p = module.app, module.app.router.prefixes[0]
    lines = [html.code(p + command.name) for item in app.modules.values() for command in item.commands]
    pages = ["<b>Elys · команды</b>\n\n" + "\n".join(lines[i:i + 25])
             + "\n\nОписание команды → " + html.code(p + "help Ping") for i in range(0, len(lines), 25)]
    # Форумные сообщения отправляет бот; страницы переключаются в том же сообщении.
    async def page(bot, pressed, index):
        await app.inline.edit(pressed, pages[index], buttons(index))

    def buttons(index):
        from elys import Button
        row = []
        if index:
            row.append(Button("‹ Назад", page, index - 1))
        if index + 1 < len(pages):
            row.append(Button("Дальше ›", page, index + 1))
        return [row] if row else []

    await app.inline.bot_form(module, query.message.chat.id, pages[0], buttons(0))
    await query.answer()
