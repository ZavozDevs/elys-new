import asyncio
import functools
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

import elys.inline.bot as bot_module
from elys.inline.bot import BotService, BotSetupError
from elys.inline.botfather import BotFatherWebApp
from tests.integration.test_loader import app as app

TOKEN = "123456:" + "x" * 35
AUTH = "query_id=fake&user=fake&hash=private-init-data"


@pytest.fixture
async def webapp(app, monkeypatch):
    state = SimpleNamespace(bots={}, titles={}, requests=[], failure=None, settings={}, durable=[],
                            response_after_create=False, chat=[], chat_reject=False, chat_log=[])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, body, status=200, *, cookie=False):
            self.send_response(status)
            if cookie:
                self.send_header("Set-Cookie", "webapp=private-cookie; Path=/botfather; HttpOnly")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self):
            path = urlsplit(self.path).path
            state.requests.append(("GET", path, {}))
            if "webapp=private-cookie" not in self.headers.get("Cookie", ""):
                if state.failure == "bootstrap":
                    return self.respond("interface changed", 400)
                return self.respond('<script>ajInit({"apiUrl":"/api?hash=private-bootstrap"})</script>', 400)
            if path == "/botfather":
                # Вёрстка как в настоящем Web App: название и username в отдельных div.
                return self.respond("".join(
                    f'<a class="tm-row tm-row-link" href="/botfather/bot/{identity}"><img class="tm-row-pic">'
                    f'<div> <div class="tm-row-value">{state.titles.get(username, "Elys")}</div>'
                    f'<div class="tm-row-description">@{username}</div> </div></a>'
                    for username, identity in state.bots.items()
                ))
            if path == "/botfather/bot/123456":
                token = "987654:" + "z" * 35 if state.failure == "token" else TOKEN
                return self.respond(f'<script>"{TOKEN}"</script><div class="tm-api-token">'
                                    f'<span>{token}</span><div class="copy-btn"></div></div>')
            self.respond("not found", 404)

        def do_POST(self):
            data = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode(), keep_blank_values=True)
            path = urlsplit(self.path)
            method = data["method"][0]
            state.requests.append(("POST", path.path, data))
            if method == "auth":
                assert data["_auth"] == [AUTH]
                assert parse_qs(path.query)["hash"] == ["private-bootstrap"]
                if state.failure == "auth":
                    return self.respond(json.dumps({"error": TOKEN + AUTH}))
                if state.failure == "redirect":
                    self.send_response(307)
                    self.send_header("Location", "https://example.org/steal-auth")
                    self.end_headers()
                    return
                if state.failure == "json":
                    return self.respond(TOKEN + AUTH)
                endpoint = ("https://example.org/api?hash=private" if state.failure == "endpoint"
                            else "/botfather/api?hash=private-session")
                if state.failure == "endpoint_type":
                    endpoint = [AUTH]
                return self.respond(json.dumps({"ok": "1", "api_url": endpoint}), cookie=True)
            assert "webapp=private-cookie" in self.headers.get("Cookie", "")
            assert parse_qs(path.query)["hash"] == ["private-session"]
            if method == "createBot":
                assert "manager_id" not in data
                assert data["title"] == ["Elys · помощник"]
                state.durable.append(dict(app.kv.ns("core")))
                if state.failure == "create":
                    return self.respond(json.dumps({"error": "Too many bots " + TOKEN + AUTH}))
                state.bots[data["username"][0]] = 123456
                if state.response_after_create:
                    return self.respond("lost create response", 502)
                return self.respond(json.dumps({"ok": True, "bot_id": "123456"}))
            if method == "changeSettings":
                assert data["bid"] == ["123456"]
                state.durable.append(dict(app.kv.ns("core")))
                if state.failure == "inline" or (state.failure == "placeholder" and "settings[inph]" in data) \
                        or (state.failure == "feedback" and "settings[infdb]" in data):
                    return self.respond(json.dumps({"error": TOKEN + AUTH}))
                state.settings.update({key: value[0] for key, value in data.items() if key.startswith("settings[")})
                return self.respond(json.dumps({"ok": True}))
            self.respond("unexpected method", 400)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(BotFatherWebApp, "ORIGIN", origin)
    app.client.get_main_web_app = AsyncMock(return_value=origin + "/botfather#" + urlencode({"tgWebAppData": AUTH}))
    # Имитация диалога с BotFather: он отвечает на каждое наше сообщение, на username — токеном.
    async def send_message(chat, text):
        assert chat == "BotFather"
        message = SimpleNamespace(id=len(state.chat) + 100 + len(state.chat_log), text=text, outgoing=True)
        state.chat_log.append(text)
        state.chat.append(message)
        reply = "Sorry, this username is invalid." if state.chat_reject and text.endswith("_bot") else "ok"
        if text.endswith("_bot") and not state.chat_reject:
            state.bots[text] = 123456
            reply = f"Done! Use this token:\n{TOKEN}"
        state.chat.append(SimpleNamespace(id=message.id + 1000, text=reply, outgoing=False))
        return message

    async def get_chat_history(chat, limit=0):
        for message in sorted(state.chat, key=lambda m: m.id, reverse=True)[:limit]:
            yield message

    async def delete_messages(chat, ids, revoke=False):
        assert revoke
        state.chat[:] = [m for m in state.chat if m.id not in ids]

    app.client.send_message = send_message
    app.client.get_chat_history = get_chat_history
    app.client.delete_messages = delete_messages
    monkeypatch.setattr(bot_module, "create_bot_in_chat",
                        functools.partial(bot_module.create_bot_in_chat, poll=0))
    app.client.listen = AsyncMock()
    app.client.unblock_user = AsyncMock()
    yield state
    await asyncio.to_thread(server.shutdown)
    server.server_close()
    thread.join()
    assert state.chat == []  # Переписка с BotFather всегда стёрта.
    app.client.listen.assert_not_called()
    app.client.unblock_user.assert_not_called()


def methods(state):
    return [data["method"][0] for kind, _, data in state.requests if kind == "POST"]


async def test_provision_over_http_saves_token_before_inline_and_skips_finished_setup(app, webapp):
    service = BotService(app)
    assert await service._provision() == TOKEN
    core = app.kv.ns("core")
    assert core["bot_token"] == core["bot_inline_token"] == core["bot_feedback"] == TOKEN
    assert core["bot_username"].endswith("_bot") and core["bot_id"] == 123456
    assert not app.kv._dirty
    assert methods(webapp) == ["auth", "createBot", "changeSettings", "changeSettings", "changeSettings"]
    assert "bot_token" not in webapp.durable[0] and webapp.durable[0]["bot_username"] == core["bot_username"]
    assert all(snapshot["bot_token"] == TOKEN for snapshot in webapp.durable[1:])
    # Inline Feedback 100% (в Web App 1 = 100%): без него бот не узнает inline_message_id формы.
    assert webapp.settings == {"settings[inline]": "1", "settings[inph]": "Elys: команды и настройки",
                               "settings[infdb]": "1"}
    count = len(webapp.requests)
    assert await service._provision() == TOKEN
    assert len(webapp.requests) == count
    app.client.get_main_web_app.assert_awaited_once_with("BotFather", "BotFather")


async def test_existing_command_created_bot_only_gets_inline_settings(app, webapp):
    core = app.kv.ns("core")
    core["bot_token"] = TOKEN  # Старые данные не требуют пересоздания бота или username.
    assert await BotService(app)._provision() == TOKEN
    assert methods(webapp) == ["auth", "changeSettings", "changeSettings", "changeSettings"]
    assert "bot_id" not in core and core["bot_feedback"] == TOKEN


async def test_bot_set_up_before_inline_feedback_gets_it_without_new_bot(app, webapp):
    core = app.kv.ns("core")
    core["bot_token"] = core["bot_inline_token"] = TOKEN  # настроен старой версией: feedback ещё не включён
    assert await BotService(app)._provision() == TOKEN
    assert methods(webapp) == ["auth", "changeSettings", "changeSettings", "changeSettings"]
    assert webapp.settings["settings[infdb]"] == "1" and core["bot_feedback"] == TOKEN
    count = len(webapp.requests)
    assert await BotService(app)._provision() == TOKEN
    assert len(webapp.requests) == count


@pytest.mark.parametrize("failure", ["token", "inline", "placeholder", "feedback"])
async def test_partial_setup_resumes_same_bot(app, webapp, failure):
    webapp.failure = failure
    with pytest.raises(BotSetupError):
        await BotService(app)._provision()
    core = app.kv.ns("core")
    assert "bot_inline_token" not in core
    assert ("bot_token" in core) == (failure in {"inline", "placeholder", "feedback"})
    assert "bot_id" in core
    username = core["bot_username"]
    assert not app.kv._dirty
    before = methods(webapp).count("createBot")
    webapp.failure = None
    assert await BotService(app)._provision() == TOKEN
    assert core["bot_username"] == username
    assert methods(webapp).count("createBot") == before
    assert not webapp.chat_log


async def test_lost_create_response_is_found_by_saved_username_without_chat(app, webapp):
    webapp.response_after_create = True
    assert await BotService(app)._provision() == TOKEN
    assert methods(webapp).count("createBot") == 1
    assert not webapp.chat_log


async def test_create_falls_back_to_newbot_chat_and_wipes_conversation(app, webapp):
    webapp.failure = "create"
    assert await BotService(app)._provision() == TOKEN
    core = app.kv.ns("core")
    username = core["bot_username"]
    assert webapp.chat_log == ["/cancel", "/newbot", "Elys · помощник", username, "/cancel"]
    assert webapp.chat == []
    assert core["bot_id"] == 123456 and core["bot_token"] == core["bot_inline_token"] == TOKEN
    # Токен взят из ответа BotFather, страницу токена Web App не открывали; остальное — через Web App.
    assert not any(path == "/botfather/bot/123456" for kind, path, _ in webapp.requests if kind == "GET")
    assert methods(webapp) == ["auth", "createBot", "changeSettings", "changeSettings", "changeSettings"]
    assert not app.kv._dirty


async def test_rejected_username_in_chat_fails_cleanly_and_resumes_same_username(app, webapp):
    webapp.failure = "create"
    webapp.chat_reject = True
    with pytest.raises(BotSetupError) as caught:
        await BotService(app)._provision()
    assert TOKEN not in str(caught.value)
    core = app.kv.ns("core")
    assert "bot_token" not in core and "bot_id" not in core
    assert webapp.chat == []
    username = core["bot_username"]
    webapp.failure = None
    webapp.chat_reject = False
    assert await BotService(app)._provision() == TOKEN
    assert core["bot_username"] == username


@pytest.mark.parametrize("failure", [
    "auth", "bootstrap", "redirect", "endpoint", "endpoint_type", "json", "create", "token", "inline", "placeholder",
    "feedback",
])
async def test_failures_do_not_leak_secrets(app, webapp, failure, caplog):
    webapp.failure = failure
    webapp.chat_reject = True  # Запасной путь через чат тоже отказывает.
    with pytest.raises(BotSetupError) as caught:
        await BotService(app)._provision()
    for secret in (TOKEN, AUTH, "private-cookie", "private-bootstrap", "private-session"):
        assert secret not in str(caught.value)
        assert secret not in caplog.text
    assert "bot_inline_token" not in app.kv.ns("core") and "bot_feedback" not in app.kv.ns("core")


async def test_webapp_link_timeout_does_not_attempt_http_or_chat(app, webapp):
    app.client.get_main_web_app.side_effect = TimeoutError(AUTH)
    with pytest.raises(BotSetupError, match="открыть Web App") as caught:
        await BotService(app)._provision()
    assert AUTH not in str(caught.value)
    assert not webapp.requests and not webapp.chat_log


@pytest.mark.parametrize("link", [
    "https://example.org/botfather#tgWebAppData=secret",
    "http://webappinternal.telegram.org/botfather#tgWebAppData=secret",
    "https://webappinternal.telegram.org.evil/botfather#tgWebAppData=secret",
    "https://webappinternal.telegram.org/other#tgWebAppData=secret",
    "https://webappinternal.telegram.org/botfather",
    "https://webappinternal.telegram.org/botfather#tgWebAppData=a&tgWebAppData=b",
])
def test_webapp_rejects_unexpected_link_without_network(link):
    with pytest.raises(BotSetupError):
        BotFatherWebApp(link)


async def test_existing_bot_by_saved_username_is_used_without_creating(app, webapp):
    webapp.bots.update({"decoy_bot": 777, "elys_saved_bot": 123456})
    app.kv.ns("core")["bot_username"] = "Elys_Saved_Bot"
    assert await BotService(app)._provision() == TOKEN
    assert "createBot" not in methods(webapp)
    assert app.kv.ns("core")["bot_id"] == 123456 and app.kv.ns("core")["bot_username"] == "elys_saved_bot"


@pytest.mark.parametrize("username, title", [("elys_1_a1b2c3_bot", "Что угодно"), ("renamed_bot", "Elys · помощник")])
async def test_own_bot_is_found_by_username_pattern_or_title(app, webapp, username, title):
    webapp.bots.update({"elysuserbot": 777, "elys_2_a1b2c3_bot": 888, username: 123456})
    webapp.titles[username] = title
    assert await BotService(app)._provision() == TOKEN
    assert "createBot" not in methods(webapp)


async def test_unrelated_bots_do_not_prevent_creation(app, webapp):
    webapp.bots.update({"elysuserbot": 777, "elys_2_a1b2c3_bot": 888})
    assert await BotService(app)._provision() == TOKEN
    assert methods(webapp).count("createBot") == 1
