import os
import platform
import re
import shutil
import socket
from html import escape
from pathlib import Path
from time import sleep

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, __version__, format_uptime, respond
from elys.ui.emoji import render

DEFAULT_INFO_MESSAGE = (
    "<blockquote><tg-emoji emoji-id=\"5256047373297164926\">E</tg-emoji>"
    "<tg-emoji emoji-id=\"5253522460808094600\">L</tg-emoji>"
    "<tg-emoji emoji-id=\"5255953012865672959\">Y</tg-emoji>"
    "<tg-emoji emoji-id=\"5256173769889718692\">S</tg-emoji>   {me}\n"
    "</blockquote>"
    "<blockquote>{e:folder} <b>Версия:</b> <code>Elys {version}</code> {build}\n"
    "{e:storm_info} <b>Хост:</b> <code>{hostname}</code>\n"
    "</blockquote>"
    "<blockquote>{e:infinity} <b>CPU:</b> <code>{cpu_cores} ядра @ {cpu_usage}%</code>\n"
    "{e:flash_ping} <b>RAM:</b> <code>{ram_used} / {ram_total} ({ram_percent}%)</code>\n"
    "{e:package} <b>Диск:</b> <code>{disk_used} / {disk_total} ({disk_percent}%)</code>\n"
    "{e:clock_uptime} <b>Uptime:</b> <code>{bot_uptime}</code>\n"
    "</blockquote>"
)

SERVINFO_TEMPLATE = (
    "<blockquote expandable>"
    "🏠 <b>Информация о сервере и окружении</b>\n\n"
    "⚙️ <b>Процессор и память</b>\n"
    "• <b>CPU:</b> <code>{cpu_cores} ядер @ {cpu_usage}%</code> ({cpu_model})\n"
    "• <b>RAM:</b> <code>{ram_used} / {ram_total} ({ram_percent}%)</code>\n"
    "• <b>Swap:</b> <code>{swap_used} / {swap_total} ({swap_percent}%)</code>\n\n"
    "📂 <b>Хранилище</b>\n"
    "• <b>Диск:</b> <code>{disk_used} / {disk_total} ({disk_percent}%)</code>\n\n"
    "ℹ️ <b>Система хоста</b>\n"
    "• <b>ОС:</b> <code>{os_name}</code>\n"
    "• <b>Ядро:</b> <code>{kernel}</code> (<code>{arch}</code>)\n"
    "• <b>Хост:</b> <code>{hostname}</code>\n"
    "• <b>Аптайм сервера:</b> <code>{system_uptime}</code>\n"
    "• <b>Load Avg:</b> <code>{load_avg}</code>\n\n"
    "🤖 <b>Процесс юзербота</b>\n"
    "• <b>Аптайм бота:</b> <code>{bot_uptime}</code>\n"
    "• <b>RAM бота:</b> <code>{proc_ram}</code>\n"
    "• <b>Python:</b> <code>{python_version}</code> · <b>Движок:</b> <code>wzgram 3.1.3</code>\n"
    "• <b>Версия:</b> <code>Elys {version}</code> {build}"
    "</blockquote>"
)

module = Module(
    "Info",
    config=Config(
        custom_message=Config.value(
            "",
            doc="Кастомный шаблон для .info (если пусто — используется фирменный стиль Elys)",
        ),
        banner=Config.url(
            "",
            doc="Картинка-баннер над ответом",
        ),
    ),
)


def _get_git_commit() -> str:
    try:
        git_dir = Path("/home/container/.git")
        if not git_dir.exists():
            git_dir = Path(__file__).resolve().parent.parent.parent / ".git"
        head_file = git_dir / "HEAD"
        if head_file.exists():
            ref = head_file.read_text("utf-8").strip()
            if ref.startswith("ref: "):
                ref_path = git_dir / ref[5:]
                if ref_path.exists():
                    commit = ref_path.read_text("utf-8").strip()[:7]
                    return f'<a href="https://github.com/ZavozDevs/elys-new/commit/{commit}">@{commit}</a>'
            elif len(ref) >= 7:
                commit = ref[:7]
                return f'<a href="https://github.com/ZavozDevs/elys-new/commit/{commit}">@{commit}</a>'
    except Exception:
        pass
    return ""


def _get_cpu_info() -> tuple[int, str]:
    cores = os.cpu_count() or 1
    model = "Unknown CPU"
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    model = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass
    return cores, model


def _get_cpu_usage() -> str:
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        if line.startswith("cpu "):
            fields = [float(x) for x in line.split()[1:]]
            idle = fields[3] + (fields[4] if len(fields) > 4 else 0.0)
            total = sum(fields)
            sleep(0.04)
            with open("/proc/stat") as f:
                line2 = f.readline()
            fields2 = [float(x) for x in line2.split()[1:]]
            idle2 = fields2[3] + (fields2[4] if len(fields2) > 4 else 0.0)
            total2 = sum(fields2)
            d_total = total2 - total
            d_idle = idle2 - idle
            if d_total > 0:
                percent = max(0.0, min(100.0, (1.0 - (d_idle / d_total)) * 100))
                return f"{percent:.1f}"
    except Exception:
        pass
    return "0.0"


def _get_ram_info() -> dict[str, str | float]:
    info: dict[str, int] = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                p = line.split(":", 1)
                if len(p) == 2:
                    info[p[0].strip()] = int(p[1].split()[0])
    except Exception:
        pass
    total_kb = info.get("MemTotal", 0)
    avail_kb = info.get("MemAvailable", info.get("MemFree", 0))
    used_kb = max(0, total_kb - avail_kb)
    percent = round((used_kb / total_kb) * 100, 1) if total_kb else 0.0

    swap_total_kb = info.get("SwapTotal", 0)
    swap_free_kb = info.get("SwapFree", 0)
    swap_used_kb = max(0, swap_total_kb - swap_free_kb)
    swap_pct = round((swap_used_kb / swap_total_kb) * 100, 1) if swap_total_kb else 0.0

    used_mb = round(used_kb / 1024)
    total_mb = round(total_kb / 1024)
    if total_mb < 2048:
        ram_str = f"{used_mb} MB / {total_mb} MB"
    else:
        ram_str = f"{used_mb / 1024:.1f} GB / {total_mb / 1024:.1f} GB"

    return {
        "used": f"{used_mb} MB",
        "total": f"{total_mb} MB",
        "formatted": ram_str,
        "percent": percent,
        "swap_used": f"{round(swap_used_kb / 1024)} MB",
        "swap_total": f"{round(swap_total_kb / 1024)} MB",
        "swap_percent": swap_pct,
    }


def _get_disk_info(path: str = "/") -> dict[str, str | float]:
    try:
        total, used, _ = shutil.disk_usage(path)
        u_gb = used / (1024**3)
        t_gb = total / (1024**3)
        pct = round((used / total) * 100, 1) if total else 0.0
        return {
            "used": f"{u_gb:.1f} GB",
            "total": f"{t_gb:.1f} GB",
            "percent": pct,
        }
    except Exception:
        return {"used": "0 GB", "total": "0 GB", "percent": 0.0}


def _get_system_uptime() -> str:
    try:
        with open("/proc/uptime") as f:
            sec = float(f.readline().split()[0])
            days, rem = divmod(int(sec), 86400)
            hours, rem = divmod(rem, 3600)
            mins, s = divmod(rem, 60)
            if days > 0:
                return f"{days}д {hours:02d}:{mins:02d}:{s:02d}"
            return f"{hours:02d}:{mins:02d}:{s:02d}"
    except Exception:
        return "Неизвестно"


def _get_process_ram() -> str:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return f"{round(kb / 1024, 1)} MB"
    except Exception:
        pass
    return "0.0 MB"


def _get_os_name() -> str:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME"):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return platform.system()


def _get_load_avg() -> str:
    try:
        l1, l5, l15 = os.getloadavg()
        return f"{l1:.2f}, {l5:.2f}, {l15:.2f}"
    except Exception:
        return "N/A"


def _collect_data(client: Client) -> dict[str, str]:
    app = getattr(module, "_app", None)
    bot_sec = getattr(app, "uptime", 0.0) if app else 0.0
    bot_uptime_str = format_uptime(bot_sec)

    cores, cpu_model = _get_cpu_info()
    cpu_usage = _get_cpu_usage()
    ram = _get_ram_info()
    disk = _get_disk_info()
    os_name = _get_os_name()
    kernel = platform.release()
    arch = platform.machine()
    sys_uptime = _get_system_uptime()
    load_avg = _get_load_avg()
    proc_ram = _get_process_ram()
    hostname = socket.gethostname()
    build = _get_git_commit()

    user_name = client.me.first_name or client.me.username or "User"
    user_handle = client.me.username
    if user_handle:
        me_link = f'<a href="https://t.me/{user_handle}">{escape(user_name)}</a>'
    else:
        me_link = f'<a href="tg://user?id={client.me.id}">{escape(user_name)}</a>'

    return {
        "version": __version__,
        "build": build,
        "me": me_link,
        "me_name": escape(user_name),
        "me_id": str(client.me.id),
        "hostname": hostname,
        "cpu_cores": str(cores),
        "cpu_model": cpu_model,
        "cpu_usage": cpu_usage,
        "ram_used": str(ram["used"]),
        "ram_total": str(ram["total"]),
        "ram_usage": str(ram["formatted"]),
        "ram_percent": str(ram["percent"]),
        "swap_used": str(ram["swap_used"]),
        "swap_total": str(ram["swap_total"]),
        "swap_percent": str(ram["swap_percent"]),
        "disk_used": str(disk["used"]),
        "disk_total": str(disk["total"]),
        "disk_percent": str(disk["percent"]),
        "os_name": os_name,
        "kernel": kernel,
        "arch": arch,
        "system_uptime": sys_uptime,
        "load_avg": load_avg,
        "bot_uptime": bot_uptime_str,
        "proc_ram": proc_ram,
        "python_version": platform.python_version(),
        "engine": "wzgram 3.1.3",
    }


@module.command("info", aliases=("i", "и"))
async def info_command(client: Client, message: Message) -> None:
    # — системная информация и статус Elys
    data = _collect_data(client)
    template = module.config["custom_message"] or DEFAULT_INFO_MESSAGE
    rendered = re.sub(r"\{(\w+)\}", lambda m: str(data.get(m.group(1), m.group(0))), template).strip()
    final_text = render(rendered, premium=bool(getattr(client.me, "is_premium", False)))
    await respond(message, final_text, banner=module.config["banner"])


@module.command("servinfo", aliases=("si", "си", "sysinfo"))
async def servinfo_command(client: Client, message: Message) -> None:
    # — подробная информация о сервере и железе
    data = _collect_data(client)
    rendered = re.sub(r"\{(\w+)\}", lambda m: str(data.get(m.group(1), m.group(0))), SERVINFO_TEMPLATE).strip()
    final_text = render(rendered, premium=bool(getattr(client.me, "is_premium", False)))
    await respond(message, final_text)
