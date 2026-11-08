# сведения о сервере и Elys без зависимостей: /proc, os, shutil, platform.

import asyncio
import os
import platform
import shutil
from contextlib import suppress
from html import escape
from pathlib import Path

import pyrogram
from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, __version__, format_uptime, respond

BANNER = "https://raw.githubusercontent.com/ZavozDevs/assets/main/elys_userbot/elys_info.png"
module = Module("Info", config=Config(banner=Config.url(BANNER, doc="Баннер")))
t = module.t
REPO = Path(__file__).resolve().parents[2]


def proc(name: str) -> dict[str, str]:
    with suppress(OSError):
        lines = Path("/proc", name).read_text().splitlines()
        return {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in lines)}
    return {}


def gb(value: float) -> str:
    return f"{value / 1024**3:.1f}"


def system() -> dict[str, str]:
    memory, disk = proc("meminfo"), shutil.disk_usage(module.app.settings.data_dir)
    total, free = (int(memory.get(k, "0").split()[0]) * 1024 for k in ("MemTotal", "MemAvailable"))
    rss = int(proc("self/status").get("VmRSS", "0").split()[0]) * 1024
    try:
        release = platform.freedesktop_os_release()["PRETTY_NAME"]
    except OSError:
        release = platform.platform()
    return {"cpu": escape(proc("cpuinfo").get("model name") or platform.machine()), "cores": str(os.cpu_count()),
            "load": f"{os.getloadavg()[0]:.2f}", "ram": gb(total - free), "ram_total": gb(total),
            "rss": f"{rss / 1024**2:.0f}", "disk": gb(disk.used), "disk_total": gb(disk.total),
            "host": escape(platform.node()), "system": escape(release)}


async def commit() -> str:
    with suppress(OSError):
        process = await asyncio.create_subprocess_exec("git", "rev-parse", "--short", "HEAD", cwd=REPO,
                                                       stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.DEVNULL)
        return (await process.communicate())[0].decode().strip()
    return ""


@module.command("info", roles=("sudo", "support"))
async def info(client: Client, message: Message) -> None:
    # — сервер и Elys: CPU, память, диск, версия, аптайм
    await respond(message, t("screen", **system(), version=__version__, commit=await commit() or "—",
                             wzgram=pyrogram.__version__, uptime=format_uptime(module.app.uptime)),
                  banner=module.config["banner"] or None)
