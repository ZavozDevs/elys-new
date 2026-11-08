import random
import re
import socket
from html import escape
from time import perf_counter

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, format_uptime, respond
from elys.ui.emoji import render

BANNER = "https://raw.githubusercontent.com/ZavozDevs/assets/main/elys_userbot/ping_cmd.png"

module = Module(
    "Ping",
    config=Config(
        custom_message=Config.value(
            "",  # пусто — шаблон языка (ping.yml: template)
            doc="Шаблон",
        ),
        ping_emoji=Config.value("🌟", doc="Эмодзи"),
        banner=Config.url(BANNER, doc="Баннер"),
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
        "fortune": random.choice(module.t("fortunes").splitlines()),
        "me": me_link,
        "hostname": socket.gethostname(),
        "now_play": "",
    }

    template = module.config["custom_message"] or module.t("template")

    # Если трек не играет / now_play пустой, убираем строку или цитату с {now_play}
    if not data["now_play"]:
        template = re.sub(r"<blockquote>[^\n<]*\{now_play\}[^\n<]*</blockquote>\n?", "", template)
        template = re.sub(r"[^\n]*\{now_play\}[^\n]*\n?", "", template)

    result = re.sub(r"\{(\w+)\}", lambda m: str(data.get(m.group(1), m.group(0))), template).strip()
    final_text = render(result, premium=bool(getattr(client.me, "is_premium", False)))

    target = reply if reply is not None else message
    await respond(target, final_text, banner=module.config["banner"])
