import asyncio
from types import SimpleNamespace

import pytest
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.parser.html import HTML
from pyrogram.types import Chat, Message

from elys.builtin.eval import module
from elys.core.router import Router
from elys.storage.kv import KV


@pytest.mark.parametrize("source", ["'😀' * 3000", "'<>&' * 1500", "await __import__('asyncio').sleep(0, 42)"])
async def test_eval_through_router_and_html_parser(tmp_path, source):
    client = Client("eval-test", api_id=1, api_hash="h", in_memory=True)
    kv = await KV.open(tmp_path / "eval.db")
    host = SimpleNamespace(client=client, router=Router(["."]), kv=kv)
    message = Message(id=1, text=f".e {source}", outgoing=True, chat=Chat(id=1, type=ChatType.PRIVATE), client=client)
    replies = []

    async def edit_text(text, **kwargs):
        replies.append(await HTML(None).parse(text))
        return message

    message.edit_text = edit_text
    await module.attach(host, group=0)
    try:
        await host.router.dispatch(client, message)
        await asyncio.gather(*module._resources.tasks)
        assert len(replies) == 1
        text = replies[0]["message"]
        assert "✅" in text
        assert len(text.encode("utf-16-le")) // 2 <= 4096
        assert "\ufffd" not in text
    finally:
        await module.detach()
        await kv.close()


class FakeInline:
    def __init__(self, fail=False):
        self.fail, self.pages = fail, None
        self.units = SimpleNamespace(remove_owner=lambda owner: None)

    async def listing(self, owner, message, pages, **kwargs):
        if self.fail:
            raise RuntimeError("бот лежит")
        self.pages = pages


async def run_long(tmp_path, source, *, inline=None, send_fails=False):
    client = Client("eval-test", api_id=1, api_hash="h", in_memory=True)
    kv = await KV.open(tmp_path / "eval.db")
    host = SimpleNamespace(client=client, router=Router(["."]), kv=kv, inline=inline, bot=object() if inline else None)
    message = Message(id=1, text=f".e {source}", outgoing=True, chat=Chat(id=1, type=ChatType.PRIVATE), client=client)
    state = SimpleNamespace(edits=[], files=[], deleted=False)

    async def edit_text(text, **kwargs):
        state.edits.append(await HTML(None).parse(text))
        return message

    async def delete(*args, **kwargs):
        state.deleted = True

    async def send_document(chat_id, document, **kwargs):
        if send_fails:
            raise RuntimeError("нет сети")
        state.files.append((document.name, document.getvalue(), kwargs["caption"]))

    message.edit_text, message.delete, client.send_document = edit_text, delete, send_document
    await module.attach(host, group=0)
    try:
        await host.router.dispatch(client, message)
        await asyncio.gather(*module._resources.tasks)
    finally:
        await module.detach()
        await kv.close()
    return state


async def test_long_output_is_paginated(tmp_path):
    inline = FakeInline()
    state = await run_long(tmp_path, "for i in range(200): print(f'{i:03}' * 30)", inline=inline)
    assert 1 < len(inline.pages) <= 10
    assert state.deleted and not state.edits and not state.files
    parsed = [(await HTML(None).parse(page))["message"] for page in inline.pages]
    assert all(len(text.encode("utf-16-le")) // 2 <= 4096 for text in parsed)
    # ничего не потеряно и не обрезано
    lines = [line for text in parsed for line in text.split("✅ ", 1)[1].splitlines()]
    assert lines == [f"{i:03}" * 30 for i in range(200)]


async def test_huge_output_or_broken_bot_goes_to_file(tmp_path):
    state = await run_long(tmp_path, "print('x' * 100_000)", inline=FakeInline())
    assert state.files and state.files[0][0] == "eval.txt" and state.files[0][1] == b"x" * 100_000
    state = await run_long(tmp_path, "print('y' * 6000)", inline=FakeInline(fail=True))
    assert state.files and state.files[0][1] == b"y" * 6000 and state.deleted
    state = await run_long(tmp_path, "print('z' * 6000)")
    assert state.files and "вывод в файле" in state.files[0][2]


async def test_truncates_when_nothing_else_works(tmp_path):
    state = await run_long(tmp_path, "print('z' * 6000)", send_fails=True)
    assert len(state.edits) == 1 and not state.deleted
    assert state.edits[0]["message"].endswith("…")
