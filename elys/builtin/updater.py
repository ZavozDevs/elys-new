# обновление из git: .update — новые коммиты и кнопка; pull --ff-only, зависимости при смене pyproject, перезапуск.

import asyncio
import sys
from html import escape
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from elys import Module, UserError, respond
from elys.inline.button import Button

module = Module("Updater")
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


def restart(chat_id: int, message_id: int, old: str) -> None:
    module.app.kv.ns("updater")["notice"] = [chat_id, message_id, old]
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
        return restart(unit.data["chat_id"], unit.data["message_id"], old)
    module.app.reboot()


@module.command("update", roles=("sudo",))
async def update(client: Client, message: Message) -> None:
    # — проверить обновления Elys и установить
    status = await respond(message, t("checking"))
    await run("git", "fetch", "--quiet")
    log = await run("git", "log", "--format=%h %s", "-n", "15", "HEAD..@{upstream}")
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
        chat_id, message_id, old = notice
        new = await run("git", "rev-parse", "--short", "HEAD")
        text = t("updated", old=old, new=new) if old else t("restarted")
        await client.edit_message_text(chat_id, message_id, text)
