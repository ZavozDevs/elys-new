import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pyrogram import StopPropagation
from pyrogram.types import User

from elys.inline.form import Inline


def install_inline(app):
    app.bot = app.client
    app.inline = Inline(app)
    app.client.me.username = "elys_test_bot"
    app.client.send_message = AsyncMock(return_value=SimpleNamespace(id=10))
    app.client.delete_messages = AsyncMock()
    app.client.send_inline_bot_result = AsyncMock()
    app.client.edit_inline_text = AsyncMock()

    async def get_results(bot, text):
        query = SimpleNamespace(query=text, from_user=app.client.me, answer=AsyncMock())
        with contextlib.suppress(StopPropagation):
            await app.inline._query(app.bot, query)
        return SimpleNamespace(query_id=7, results=query.answer.call_args.args[0])

    app.client.get_inline_bot_results = get_results


def last_unit(app):
    return next(reversed(app.inline.units.items.values()))


def query_for(unit, text, *, user_id=1):
    index = next(i for i, button in unit.buttons.items() if button.text == text)
    return SimpleNamespace(data=f"{unit.id}:{index}", from_user=User(id=user_id),
                           inline_message_id="inline-message", answer=AsyncMock(),
                           edit_message_text=AsyncMock(), edit_message_media=AsyncMock(),
                           edit_message_caption=AsyncMock())


async def click(app, unit, text):
    query = query_for(unit, text)
    await app.inline._run(unit, query, int(query.data.split(":")[1]))
    return query
