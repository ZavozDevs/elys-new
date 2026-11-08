# обновление из git: .update — новые коммиты и кнопка; pull --ff-only, зависимости при смене pyproject, перезапуск.
# Проверка — хеш через GitHub API с ETag (304 не тратит лимит); git fetch только когда хеш новый.

import asyncio
import contextlib
import re
import sys
import time
from html import escape
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, UserError, respond
from elys.inline.button import Button

module = Module("Updater", config=Config(
    check=Config.integer(6, min=0, doc="Проверять обновления раз в N часов, 0 — выключено")))
t = module.t
REPO = Path(__file__).resolve().parents[2]


async def run(*command: str) -> str:
    # аргументы фиксированы в коде — ввод пользователя в shell не попадает
    process = await asyncio.create_subprocess_exec(*command, cwd=REPO, stdin=asyncio.subprocess.DEVNULL,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    output = (await process.communicate())[0].decode(errors="replace").strip()
    if process.returncode:
        raise UserError(t("failed", output=escape(output[-1500:] or str(process.returncode))))
    return output


def head(url: str, etag: str | None) -> tuple[str | None, str | None]:
    # 40 байт хеша вместо JSON; «не изменилось» (304) — без тела
    headers = {"Accept": "application/vnd.github.sha", "User-Agent": "Elys"}
    if etag:
        headers["If-None-Match"] = etag
    try:
        with urlopen(Request(url, headers=headers), timeout=15) as response:
            return response.read().decode().strip(), response.headers.get("ETag")
    except HTTPError as error:
        if error.code == 304:
            return None, etag
        raise


async def remote() -> str | None:
    # хеш ветки на GitHub; None — не удалось узнать (не GitHub, нет сети, лимит)
    state = module.app.kv.ns("updater")
    try:
        slug = re.search(r"github\.com[:/](.+?)(?:\.git)?/?$", await run("git", "remote", "get-url", "origin"))
        branch = (await run("git", "rev-parse", "--abbrev-ref", "@{upstream}")).split("/", 1)[1]
        if not slug:
            return None
        sha, etag = await asyncio.to_thread(
            head, "https://api.github.com/repos/" + slug[1] + "/commits/" + branch, state.get("etag"))
    except (UserError, OSError, IndexError):
        return None
    if sha:
        state["sha"], state["etag"] = sha, etag
    return state.get("sha")


async def pending() -> str:
    # новые коммиты; fetch — только если хеш на GitHub отличается от уже скачанного
    sha = await remote()
    if sha is None or sha != await run("git", "rev-parse", "@{upstream}"):
        await run("git", "fetch", "--quiet")
    return await run("git", "log", "--format=%h %s", "-n", "15", "HEAD..@{upstream}")


def restart(chat_id: int, message_id: int, old: str, direct: bool = False) -> None:
    module.app.kv.ns("updater")["notice"] = [chat_id, message_id, old, direct]
    module.app.reboot()


async def install(bot, query, _) -> None:
    unit = module.app.inline.from_query(query)
    old = await run("git", "rev-parse", "--short", "HEAD")
    await module.app.inline.edit(query, t("installing"))
    try:
        await run("git", "pull", "--ff-only", "--quiet")
        if "pyproject.toml" in (await run("git", "diff", "--name-only", old, "HEAD")).split():
            try:
                await run(sys.executable, "-m", "pip", "install", "--quiet", "-e", ".")
            except UserError:
                await run("git", "reset", "--keep", old)  # без зависимостей новый код не запустится
                raise
    except UserError as error:
        return await module.app.inline.edit(query, str(error))
    if unit and unit.data.get("message_id"):
        return restart(unit.data["chat_id"], unit.data["message_id"], old, bool(unit.data.get("direct")))
    module.app.reboot()


@module.command("update", roles=("sudo",))
async def update(client: Client, message: Message) -> None:
    # — проверить обновления Elys и установить
    status = await respond(message, t("checking"))
    log = await pending()
    if not log:
        return await respond(status, t("latest", version=await run("git", "rev-parse", "--short", "HEAD")))
    await module.app.inline.form(module, message, t("available", log=escape(log)),
                                 [[Button(t("install"), install, style="success", icon="check")]])
    if status.outgoing and not status.deleted:
        await status.delete()


@module.command("restart", roles=("sudo",))
async def reboot(client: Client, message: Message) -> None:
    # — перезапустить Elys
    status = await respond(message, t("restarting"))
    restart(status.chat.id, status.id, "")


@module.on_ready
async def notify(client: Client) -> None:
    # после перезапуска правим то самое сообщение
    notice = module.app.kv.ns("updater").pop("notice", None)
    if notice:
        chat_id, message_id, old, *direct = notice
        new = await run("git", "rev-parse", "--short", "HEAD")
        text = t("updated", old=old, new=new) if old else t("restarted")
        if direct and direct[0]:  # уведомление отправил бот — и правит бот
            await module.app.bot.edit_message_text(chat_id, message_id, module.app.inline._text(text))
        else:
            await client.edit_message_text(chat_id, message_id, text)


@module.loop(600, autostart=True)
async def watch(client: Client) -> None:
    # раз в N часов (время в KV — перезапуск не сбивает); одно уведомление на версию, старое удаляется
    state, hours = module.app.kv.ns("updater"), module.config["check"]
    if not hours or time.time() - state.get("checked", 0) < hours * 3600 or not module.app.bot:
        return
    state["checked"] = time.time()
    sha = await remote()
    if not sha or sha == state.get("notified") or sha == await run("git", "rev-parse", "HEAD"):
        return
    log = await pending()
    state["notified"] = sha
    if not log:
        return
    if state.get("message"):
        with contextlib.suppress(Exception):
            await module.app.bot.delete_messages(*state["message"])
    forum = module.app.forum
    chat, thread = ((forum.chat_id, forum.state["topics"].get("updates")) if forum and forum.available
                    else (client.me.id, None))
    unit = await module.app.inline.bot_form(module, chat, t("available", log=escape(log)),
                                            [[Button(t("install"), install, style="success", icon="check")]],
                                            ttl=30 * 86400, thread=thread)
    state["message"] = [chat, unit.data["message_id"]]
