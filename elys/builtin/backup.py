# резервная копия: база и файлы модулей (без сессий и settings.toml) — только в тему «Копии» или Избранное.
# Автокопия — раз в N часов, только в форум и только если данные изменились; хранятся последние K.

import asyncio
import contextlib
import hashlib
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, UserError, get_reply, respond

module = Module("Backup", config=Config(
    interval=Config.integer(24, min=0, doc="Автокопия раз в N часов, 0 — выключено"),
    keep=Config.integer(7, min=1, doc="Сколько автокопий хранить"),
))
t = module.t


SERVICE = ("backup", "updater")  # служебные отметки времени не делают копию «новой»


def pack(data: Path, target: Path) -> str:
    # архив и отпечаток содержимого (записи KV + файлы модулей)
    snapshot = target.with_suffix(".db")
    with contextlib.closing(sqlite3.connect(data / "elys.db")) as source:
        source.execute("VACUUM INTO ?", (str(snapshot),))  # согласованный и сжатый снимок живой базы
    digest = hashlib.sha256()
    with contextlib.closing(sqlite3.connect(snapshot)) as copy:
        for row in copy.execute("SELECT ns, key, value FROM kv WHERE ns NOT IN (?, ?) ORDER BY ns, key", SERVICE):
            digest.update(repr(row).encode())
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(snapshot, "elys.db")
        for path in sorted((data / "modules").glob("*.py")):
            archive.write(path, f"modules/{path.name}")
            digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def name() -> str:
    return f"elys-{datetime.now():%Y-%m-%d-%H%M}.zip"


async def upload(forum, archive: Path):
    return await module.app.bot.send_document(forum.chat_id, archive, caption=t("caption"), disable_notification=True,
                                              message_thread_id=forum.state["topics"].get("backups"))


@module.command("backup", roles=("sudo",))
async def backup(client: Client, message: Message) -> None:
    # — копия базы и модулей в тему «Копии» (в чат копия не попадает)
    app = module.app
    await app.kv.flush()
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / name()
        await asyncio.to_thread(pack, app.settings.data_dir, archive)
        forum = getattr(app, "forum", None)
        if forum is not None and forum.available:
            await upload(forum, archive)
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


@module.loop(3600, autostart=True)
async def auto(client: Client) -> None:
    # время, отпечаток и id сообщений — в KV: перезапуск не сбивает расписание и не шлёт повторов
    app, state, hours = module.app, module.app.kv.ns("backup"), module.config["interval"]
    forum = getattr(app, "forum", None)
    if not hours or forum is None or not forum.available or time.time() - state.get("last", 0) < hours * 3600:
        return  # без форума автокопий нет: в базе токен бота, в чаты её не шлём
    state["last"] = time.time()
    await app.kv.flush()
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / name()
        digest = await asyncio.to_thread(pack, app.settings.data_dir, archive)
        if digest == state.get("digest"):
            return
        sent = await upload(forum, archive)
    messages = [*state.get("messages", []), [forum.chat_id, sent.id]]
    keep = module.config["keep"]
    for chat_id, message_id in messages[:-keep]:
        with contextlib.suppress(Exception):  # уже удалено вручную или форум пересоздан
            await app.bot.delete_messages(chat_id, message_id)
    state["digest"], state["messages"] = digest, messages[-keep:]
