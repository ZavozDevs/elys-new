import random
import re
import socket
from html import escape
from time import perf_counter

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, format_uptime, respond
from elys.ui.emoji import render

# Дефолтный классический дизайн Elys / Heroku:
DEFAULT_PING_MESSAGE = (
    "<blockquote>{e:flash_ping} <b>Понг:</b> <code>{ping}</code> <b>𝚖𝚜</b>\n"
    "{e:clock_uptime} <b>𝚄𝚙𝚝𝚒𝚖𝚎:</b> <code>{uptime}</code></blockquote>"
)

FORTUNES = (
    "Как всегда — прекрасно",
    "Вы великолепны",
    "Ваш пинг, как и заказывали",
    "Пинг — скорость ответа Telegram",
    "Приятного использования!",
    "Спасибо, пользователь!",
    "Круто, когда всё хорошо",
    "Работает стабильно и шустро",
    "Elys на связи ✨",
)

module = Module(
    "Ping",
    config=Config(
        custom_message=Config.value(
            DEFAULT_PING_MESSAGE,
            doc="Шаблон пинга ({ping}, {uptime}, {fortune}, {me}, {hostname})",
        ),
        ping_emoji=Config.value("🌟", doc="Эмодзи или текст во время замера пинга"),
        banner=Config.url("", doc="Картинка-баннер над ответом"),
    ),
)


@module.command("ping", aliases=("p", "пинг"))
async def ping(client: Client, message: Message) -> None:
    # — задержка ответа telegram и аптайм
    start = perf_counter()
    raw_emoji = module.config["ping_emoji"] or "🌟"
    emoji_rendered = render(raw_emoji, premium=bool(getattr(client.me, "is_premium", False)))
    reply = await respond(message, emoji_rendered)

    ping_ms = round((perf_counter() - start) * 1000, 2)

    app = getattr(module, "_app", None)
    bot_sec = getattr(app, "uptime", 0.0) if app else 0.0
    uptime_str = format_uptime(bot_sec)

    user_name = client.me.first_name or client.me.username or "User"
    user_handle = client.me.username
    if user_handle:
        me_link = f'<a href="https://t.me/{user_handle}">{escape(user_name)}</a>'
    else:
        me_link = f'<a href="tg://user?id={client.me.id}">{escape(user_name)}</a>'

    data = {
        "ping": f"{ping_ms:.1f}",
        "uptime": uptime_str,
        "fortune": random.choice(FORTUNES),
        "me": me_link,
        "hostname": socket.gethostname(),
        "now_play": "",
    }

    template = module.config["custom_message"] or DEFAULT_PING_MESSAGE

    # Если трек не играет / now_play пустой, убираем строку или цитату с {now_play}
    if not data["now_play"]:
        template = re.sub(r"<blockquote>[^\n<]*\{now_play\}[^\n<]*</blockquote>\n?", "", template)
        template = re.sub(r"[^\n]*\{now_play\}[^\n]*\n?", "", template)

    result = re.sub(r"\{(\w+)\}", lambda m: str(data.get(m.group(1), m.group(0))), template).strip()
    final_text = render(result, premium=bool(getattr(client.me, "is_premium", False)))

    target = reply if reply is not None else message
    await respond(target, final_text, banner=module.config["banner"])
