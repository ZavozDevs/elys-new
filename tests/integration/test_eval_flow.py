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
