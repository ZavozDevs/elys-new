# резервная копия: база и файлы модулей (без сессий и settings.toml) — только в тему «Копии» или Избранное.

import asyncio
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from elys import Module, UserError, get_reply, respond

module = Module("Backup")
t = module.t


def pack(data: Path, target: Path) -> None:
    snapshot = target.with_suffix(".db")
    with sqlite3.connect(data / "elys.db") as source, sqlite3.connect(snapshot) as copy:
        source.backup(copy)  # согласованный снимок живой базы
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(snapshot, "elys.db")
        for path in sorted((data / "modules").glob("*.py")):
            archive.write(path, f"modules/{path.name}")


@module.command("backup", roles=("sudo",))
async def backup(client: Client, message: Message) -> None:
    # — копия базы и модулей в тему «Копии» (в чат копия не попадает)
    app = module.app
    await app.kv.flush()
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / f"elys-{datetime.now():%Y-%m-%d-%H%M}.zip"
        await asyncio.to_thread(pack, app.settings.data_dir, archive)
        forum = getattr(app, "forum", None)
        if forum is not None and forum.available:
            await app.bot.send_document(forum.chat_id, archive, caption=t("caption"), disable_notification=True,
                                        message_thread_id=forum.state["topics"].get("backups"))
        else:
            await client.send_document("me", archive, caption=t("caption"))
    await respond(message, t("done"))


@module.command("restore", roles=("sudo",))
async def restore(client: Client, message: Message) -> None:
    # — в ответ на файл копии: восстановить и перезапустить
    reply = await get_reply(message)
    if reply is None or reply.document is None:
        raise UserError(t("no_file"))
    pending = module.app.settings.data_dir / "restore.zip"
    await reply.download(str(pending))
    try:
        with zipfile.ZipFile(pending) as archive:
            valid = "elys.db" in archive.namelist() and archive.testzip() is None  # лишнее отсеет restore_pending
    except zipfile.BadZipFile:
        valid = False
    if not valid:
        pending.unlink(missing_ok=True)
        raise UserError(t("bad_file"))
    await respond(message, t("restoring"))
    module.app.reboot()
