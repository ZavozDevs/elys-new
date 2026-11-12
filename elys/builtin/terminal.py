# shell сервера: .t <команда> — вывод обновляется на лету; .t в ответ на её сообщение — остановить.

import asyncio
import os
import signal
from contextlib import suppress
from html import escape
from time import monotonic

from pyrogram import Client
from pyrogram.types import Message

from elys import Config, Module, UserError, get_reply, raw_args, respond

module = Module("Terminal", config=Config(timeout=Config.integer(300, min=0, doc="Лимит, с")))
t = module.t
LIMIT = 3500  # хвост вывода — в лимит сообщения telegram
running: dict[tuple[int, int], asyncio.subprocess.Process] = {}


def screen(command: str, output: bytes, code: str) -> str:
    text = output.decode(errors="replace")[-LIMIT:] or t("no_output")
    return t("screen", command=escape(command[:300]), output=escape(text), code=code)


@module.command("t", aliases=("terminal",), roles=("sudo",))
async def terminal(client: Client, message: Message) -> None:
    # <команда> — выполнить в shell сервера; без аргументов в ответ — остановить
    command = raw_args(message).strip()
    if not command:
        reply = await get_reply(message)
        process = running.get((reply.chat.id, reply.id)) if reply else None
        if process is None:
            raise UserError(t("usage"))
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        return
    status = await respond(message, screen(command, b"", t("running")))
    process = await asyncio.create_subprocess_shell(
        command,
        stdin=asyncio.subprocess.DEVNULL,
        start_new_session=True,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    running[status.chat.id, status.id] = process
    output, shown, code = b"", monotonic(), t("running")
    try:
        async with asyncio.timeout(module.config["timeout"] or None):
            while chunk := await process.stdout.read(4096):
                output = (output + chunk)[-4 * LIMIT :]
                if monotonic() - shown > 3:  # не чаще раза в 3 с: лимит правок telegram
                    shown = monotonic()
                    status = await respond(status, screen(command, output, code))
            code = str(await process.wait())
    except TimeoutError:
        code = t("timeout")
    finally:
        running.pop((status.chat.id, status.id), None)
        if process.returncode is None:  # таймаут или выгрузка модуля: гасим всю группу процессов
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
    await respond(status, screen(command, output, code))
