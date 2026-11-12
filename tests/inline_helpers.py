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
    app.client.send_inline_bot_result = AsyncMock(return_value=SimpleNamespace(id=555))
    app.client.edit_inline_text = AsyncMock()

    async def get_results(bot, text):
        query = SimpleNamespace(query=text, from_user=app.client.me, answer=AsyncMock())
        with contextlib.suppress(StopPropagation):
            await app.inline._query(app.bot, query)
        return SimpleNamespace(query_id=7, results=query.answer.call_args.args[0])

    app.client.get_inline_bot_results = get_results


async def type_value(app, unit, text, value):
    # ввод через бота: «@бот cfg <форма>:<кнопка> значение» → выбор подсказки → «⏳» удаляется
    from elys.builtin import configure

    index = next(i for i, b in unit.buttons.items() if b.query is not None and b.text == text)
    sent = SimpleNamespace(
        outgoing=False, from_user=app.client.me, via_bot=app.bot.me, delete=AsyncMock()
    )  # как в «Избранном»

    async def history(chat_id, limit=0):
        yield sent

    app.client.get_chat_history = history
    await configure.input_value(app.bot, SimpleNamespace(query=f"cfg {unit.id}:{index} {value}"))
    return sent


def last_unit(app):
    return next(reversed(app.inline.units.items.values()))


def query_for(unit, text, *, user_id=1):
    index = next(i for i, button in unit.buttons.items() if button.text.split(" · ")[0] == text)
    return SimpleNamespace(
        data=f"{unit.id}:{index}",
        from_user=User(id=user_id),
        inline_message_id="inline-message",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_media=AsyncMock(),
        edit_message_caption=AsyncMock(),
    )


async def click(app, unit, text):
    query = query_for(unit, text)
    await app.inline._run(unit, query, int(query.data.split(":")[1]))
    return query
