from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChannelPrivate, UserIsBlocked, UserNotParticipant

from elys.inline.bot import BotService, BotSetupError
from elys.inline.forum import TOPICS, Forum
from tests.integration.test_loader import app as app

TOKEN = "123456:" + "x" * 35  # искусственный токен, никогда не используется для сети


@pytest.mark.parametrize("failure", [None, "verify", "identity"])
async def test_bot_service_start_cleanup_and_private_session(app, monkeypatch, tmp_path, failure):
    from elys.inline import bot as bot_module

    core = app.kv.ns("core")
    core["bot_token"] = core["bot_inline_token"] = core["bot_feedback"] = TOKEN
    core["bot_verified"] = 123456
    database = tmp_path / "bot.session"
    database.touch()
    database.chmod(0o644)
    handlers = []
    bot = SimpleNamespace(
        me=SimpleNamespace(id=99 if failure == "identity" else 123456, is_bot=True),
        is_initialized=True, start=AsyncMock(), stop=AsyncMock(), storage=SimpleNamespace(database=database),
        add_handler=lambda handler, group: handlers.append((handler, group)),
    )
    monkeypatch.setattr(bot_module, "BotClient", lambda *a, **kw: bot)
    service = BotService(app)
    service.verify = AsyncMock(side_effect=BotSetupError("probe failed") if failure == "verify" else None)
    if failure == "verify":
        core.pop("bot_verified")
    if failure:
        with pytest.raises(BotSetupError):
            await service.start()
        assert app.bot is None
        # Чужая сессия откладывается в сторону и бот запускается ещё раз; повторный сбой — ошибка.
        assert bot.stop.await_count == (2 if failure == "identity" else 1)
    else:
        assert await service.start() is bot
        service.verify.assert_not_called()
        assert handlers and app.bot is bot
        await service.stop()
        bot.stop.assert_awaited_once()
        assert app.bot is None
        assert database.stat().st_mode & 0o777 == 0o600


def bot_for(app):
    bot = SimpleNamespace(me=SimpleNamespace(id=123456, username="elys_test_bot"),
                          send_message=AsyncMock(return_value=SimpleNamespace(id=12)))
    app.bot = bot
    service = BotService(app)
    service.client = bot
    app.bot_service = service
    app.client.unblock_user = AsyncMock()
    app.client.get_users = AsyncMock()
    app.client.delete_messages = AsyncMock()
    return service, bot


async def test_start_probe_owner_only_cleanup_and_forum_link(app):
    service, bot = bot_for(app)
    app.forum = SimpleNamespace(url="https://t.me/c/77/1")
    async def send(peer, text):
        assert peer == bot.me.username and text == "/start"
        await service._private(bot, SimpleNamespace(from_user=app.client.me, text=text,
                                                    chat=SimpleNamespace(id=1)))
        return SimpleNamespace(id=11)
    app.client.send_message = send
    await service.verify()
    app.client.delete_messages.assert_awaited_once_with(bot.me.username, [11, 12], revoke=True)
    assert app.kv.ns("core")["bot_verified"] == bot.me.id
    assert bot.send_message.call_args.kwargs["reply_markup"].inline_keyboard[0][0].url == app.forum.url
    bot.send_message.reset_mock()
    await service._private(bot, SimpleNamespace(from_user=SimpleNamespace(id=99)))
    bot.send_message.assert_not_called()


async def test_private_fallback_unblocks_and_reprobes(app):
    service, bot = bot_for(app)
    calls = []
    async def send_bot(peer, text, **kwargs):
        calls.append(text)
        if len(calls) == 1:
            raise UserIsBlocked
        return SimpleNamespace(id=12)
    bot.send_message = send_bot
    async def send_user(peer, text):
        await service._private(bot, SimpleNamespace(from_user=app.client.me, text=text,
                                                    chat=SimpleNamespace(id=1)))
        return SimpleNamespace(id=11)
    app.client.send_message = send_user
    result = await service.send_private("Важное сообщение")
    assert result.id == 12
    assert calls[0] == calls[-1] == "Важное сообщение"
    assert len(calls) == 3
    app.client.unblock_user.assert_awaited_once_with(bot.me.username)


async def test_failed_probe_does_not_mark_verified_and_deletes_request(app):
    service, bot = bot_for(app)
    async def send(peer, text):
        service._probe.set_exception(TimeoutError())
        return SimpleNamespace(id=11)
    app.client.send_message = send
    with pytest.raises(BotSetupError, match="10 секунд"):
        await service.verify()
    assert "bot_verified" not in app.kv.ns("core")
    app.client.delete_messages.assert_awaited_once_with(bot.me.username, [11], revoke=True)


def forum_transport(app):
    # topics: {id чата: {id темы: название}}; forums — диалоги владельца; members — боты-участники по чатам.
    topics, forums, members, intros = {}, [], {}, {}
    ids = iter([-10077, -10088])
    async def create_group(title, about, is_forum=False):
        chat = SimpleNamespace(id=next(ids), title=title, is_forum=True, is_creator=True)
        forums.append(chat)
        return chat
    app.client.create_supergroup = AsyncMock(side_effect=create_group)
    async def owned_forums(title):
        return [c.id for c in forums if c.is_forum and c.is_creator and c.title == title]
    app.client.owned_forums = owned_forums
    async def chat_members(chat_id):
        for identity in members.get(chat_id, []):
            yield SimpleNamespace(user=SimpleNamespace(id=identity, is_bot=True, is_deleted=False))
    app.client.get_chat_members = chat_members
    async def search(chat_id, query="", top_msg_id=None, limit=0):
        for message in intros.get((chat_id, top_msg_id), []):
            yield message
    app.client.search_messages = search
    app.client.get_chat = AsyncMock(return_value=SimpleNamespace(is_forum=True))
    app.client.get_chat_member = AsyncMock(return_value=SimpleNamespace(status=ChatMemberStatus.ADMINISTRATOR))
    app.client.add_chat_members = AsyncMock()
    app.client.promote_chat_member = AsyncMock()
    app.client.unban_chat_member = AsyncMock()
    async def get_topics(chat_id):
        for identity, title in topics.setdefault(chat_id, {1: "General"}).items():
            yield SimpleNamespace(id=identity, title=title)
    app.client.get_forum_topics = get_topics
    async def create_topic(chat_id, title):
        values = topics.setdefault(chat_id, {1: "General"})
        identity = max(values) + 1
        values[identity] = title
        return SimpleNamespace(id=identity)
    app.bot = SimpleNamespace(
        me=SimpleNamespace(id=2, username="bot"), get_chat=AsyncMock(), edit_general_forum_topic=AsyncMock(),
        create_forum_topic=AsyncMock(side_effect=create_topic),
        send_message=AsyncMock(return_value=SimpleNamespace(id=20)),
        pin_chat_message=AsyncMock(),
    )
    app.bot_service = SimpleNamespace(send_private=AsyncMock(return_value=SimpleNamespace(id=30)))
    return SimpleNamespace(topics=topics, forums=forums, members=members, intros=intros)


def existing_forum(fx, chat_id, bots=(), title="Elys", creator=True):
    fx.forums.append(SimpleNamespace(id=chat_id, title=title, is_forum=True, is_creator=creator))
    fx.members[chat_id] = list(bots)


async def test_forum_creation_idempotence_missing_topic_and_deleted_forum(app):
    topics = forum_transport(app).topics
    forum = await Forum(app).ensure()
    assert forum.chat_id == -10077 and forum.url == "https://t.me/c/77/1"
    assert set(forum.state["topics"]) == {"errors", "updates", "backups"}
    assert app.bot.create_forum_topic.await_count == 3
    privileges = app.client.promote_chat_member.call_args.kwargs["privileges"]
    assert privileges.can_manage_topics and privileges.can_delete_messages
    assert all(c.kwargs["disable_notification"] for c in app.bot.send_message.call_args_list)
    await Forum(app).ensure()
    app.client.create_supergroup.assert_awaited_once()
    app.client.add_chat_members.assert_awaited_once()
    assert app.bot.create_forum_topic.await_count == 3
    topics[-10077].pop(forum.state["topics"]["errors"])
    recovered = await Forum(app).ensure()
    assert app.bot.create_forum_topic.await_count == 4
    assert recovered.state["topics"]["errors"] != forum.state["topics"]["errors"]
    app.client.get_chat.side_effect = ChannelPrivate
    recreated = await Forum(app).ensure()
    assert recreated.chat_id == -10088
    assert "welcome" not in recreated.state
    assert app.client.create_supergroup.await_count == 2
    assert app.kv.ns("core")["forum"]["id"] == -10088


@pytest.mark.parametrize("gone", ["not_participant", "left", "banned"])
async def test_expelled_bot_returns_to_same_forum_and_network_error_changes_nothing(app, gone):
    forum_transport(app)
    await Forum(app).ensure()
    app.client.get_chat.side_effect = TimeoutError("network")
    with pytest.raises(TimeoutError):
        await Forum(app).ensure()
    assert app.client.create_supergroup.await_count == 1
    app.client.get_chat.side_effect = None
    if gone == "not_participant":
        app.client.get_chat_member.side_effect = UserNotParticipant
    else:
        status = ChatMemberStatus.LEFT if gone == "left" else ChatMemberStatus.BANNED
        app.client.get_chat_member.return_value = SimpleNamespace(status=status)
    forum = await Forum(app).ensure()
    # Форум жив — новый не создаётся, бот возвращается (из бана — сначала разбан), темы не дублируются.
    assert forum.chat_id == -10077
    app.client.create_supergroup.assert_awaited_once()
    assert app.client.add_chat_members.await_count == 2
    assert app.client.unban_chat_member.await_count == (gone == "banned")
    assert app.bot.create_forum_topic.await_count == 3


async def test_existing_forum_is_adopted_with_its_topics_and_intros(app):
    fx = forum_transport(app)
    existing_forum(fx, -10050, bots=[2])
    existing_forum(fx, -10060, bots=[], title="Elys чат")
    existing_forum(fx, -10070, bots=[], creator=False)
    fx.topics[-10050] = {1: "👋 Начало", 40: "⚠️ Ошибки", 41: "обновления", 42: "Чужая тема"}
    intro = TOPICS["errors"][1]
    fx.intros[(-10050, 40)] = [SimpleNamespace(id=500, text=intro)]
    forum = await Forum(app).ensure()
    app.client.create_supergroup.assert_not_awaited()
    assert forum.chat_id == -10050
    assert forum.state["topics"] == {"errors": 40, "updates": 41, "backups": 43}
    # создана только недостающая тема, вводное найденной темы не продублировано
    assert app.bot.create_forum_topic.await_count == 1
    assert forum.state["intros"]["errors"] == 500
    sent = [c.kwargs["message_thread_id"] for c in app.bot.send_message.call_args_list]
    assert sorted(sent) == [41, 43]
    app.bot.edit_general_forum_topic.assert_not_awaited()
    assert app.kv.ns("core")["forum"]["id"] == -10050


async def test_forum_with_our_bot_is_preferred_and_orphan_forum_is_adopted_otherwise(app):
    fx = forum_transport(app)
    existing_forum(fx, -10050, bots=[])  # осиротевший: бот удалён
    existing_forum(fx, -10051, bots=[2])
    assert (await Forum(app).ensure()).chat_id == -10051
    app.kv.ns("core").pop("forum")
    fx.members[-10051] = []
    assert (await Forum(app).ensure()).chat_id == -10050
    app.client.create_supergroup.assert_not_awaited()


async def test_unavailable_saved_forum_is_not_readopted(app):
    fx = forum_transport(app)
    forum = await Forum(app).ensure()
    app.client.get_chat.side_effect = ChannelPrivate
    assert forum.chat_id == -10077 and fx.forums[0].id == -10077
    assert (await Forum(app).ensure()).chat_id == -10088


async def test_forum_delivery_falls_back_and_detects_extra_members(app):
    forum_transport(app)
    forum = await Forum(app).ensure()
    app.bot.send_message.side_effect = ChannelPrivate
    assert (await forum.send("errors", "Ошибка")).id == 30
    assert not forum.available
    app.bot_service.send_private.assert_awaited_once_with("Ошибка", disable_notification=True)
    async def members(chat_id):
        for identity in [1, 2, 3]:
            yield SimpleNamespace(user=SimpleNamespace(id=identity))
    app.client.get_chat_members = members
    assert not await forum.is_private()


@pytest.mark.parametrize("error", ["AccessTokenInvalid", "UserDeactivated"])
async def test_dead_token_forgets_bot_sets_session_aside_and_finds_bot_again(app, monkeypatch, error):
    from pyrogram import errors

    from elys.inline import bot as bot_module

    core = app.kv.ns("core")
    core.update({"bot_token": TOKEN, "bot_inline_token": TOKEN, "bot_feedback": TOKEN, "bot_id": 123456,
                 "bot_username": "gone_bot", "bot_verified": 123456})
    session = app.settings.data_dir / "bot.session"
    session.write_text("old")
    fresh = "654321:" + "y" * 35
    tokens = []

    def make_client(*args, bot_token, **kwargs):
        tokens.append(bot_token)
        broken = len(tokens) == 1
        client = SimpleNamespace(
            me=SimpleNamespace(id=int(bot_token.split(":")[0]), is_bot=True), is_initialized=True,
            stop=AsyncMock(), storage=SimpleNamespace(database=session), add_handler=lambda *a: None)
        client.start = AsyncMock(side_effect=getattr(errors, error) if broken else None)
        return client

    monkeypatch.setattr(bot_module, "BotClient", make_client)
    service = BotService(app)

    async def provision():
        # после забывания бот ищется заново: подставляем найденного
        if "bot_token" not in core:
            core.update({"bot_token": fresh, "bot_inline_token": fresh, "bot_feedback": fresh, "bot_verified": 654321})
        return core["bot_token"]

    service._provision = provision
    assert (await service.start()).me.id == 654321
    assert tokens == [TOKEN, fresh]
    assert "gone_bot" not in core.values() and "bot_username" not in core
    assert not session.exists() and session.with_name("bot.session.old").read_text() == "old"
