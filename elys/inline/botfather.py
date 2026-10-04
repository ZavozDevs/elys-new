"""Внутренний HTTPS API официального Web App BotFather; без команд и браузера."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

TOKEN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")
log = logging.getLogger(__name__)
_BOT_PATH = re.compile(r"/botfather/bot/(\d+)")
_API_URL = re.compile(r'"apiUrl"\s*:\s*("(?:[^"\\]|\\.)*")')
_LIMIT = 2 << 20
BOT_TITLE = "Elys · помощник"


class BotSetupError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Авторизация и cookies никогда не должны уйти на другой адрес.
        return None


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bots = {}
        self.titles = {}
        self.tokens = []
        self._link = None
        self._title = None
        self._token_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "a":
            self._link = (attrs.get("href", ""), [], [])
        if tag == "div":
            if self._token_depth:
                self._token_depth += 1
            elif "tm-api-token" in classes:
                self._token_depth = 1
            elif self._link and "tm-row-value" in classes:
                self._title = self._link[2]

    def handle_endtag(self, tag):
        if tag == "a" and self._link:
            href, text, title = self._link
            path = _BOT_PATH.fullmatch(href)
            username = re.search(r"@([A-Za-z0-9_]+)", "".join(text))
            if path and username:
                self.bots[username[1].lower()] = int(path[1])
                self.titles[username[1].lower()] = "".join(title).strip()
            self._link = self._title = None
        if tag == "div":
            self._title = None
            if self._token_depth:
                self._token_depth -= 1

    def handle_data(self, data):
        if self._link:
            self._link[1].append(data)
        if self._title is not None:
            self._title.append(data)
        if self._token_depth:
            self.tokens.append(data)


async def create_bot_in_chat(client, username, *, reply_wait=20, poll=1.0):
    """Создаёт бота командой /newbot и возвращает токен; затем удаляет всю переписку.

    Запасной путь на случай, когда createBot в Web App отказывает. Токен появляется в чате
    с BotFather, поэтому все сообщения после стартовой точки (наши и его) стираются у обоих.
    Тексты ответов BotFather не разбираются: нужен только токен в последнем ответе.
    """
    async def history():
        return [m async for m in client.get_chat_history("BotFather", limit=20)]

    async def say(text):
        sent = await client.send_message("BotFather", text)
        deadline = asyncio.get_running_loop().time() + reply_wait
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(poll)
            replies = [m for m in await history() if m.id > sent.id and not m.outgoing]
            if replies:
                return " ".join((m.text or "") for m in replies)
        raise BotSetupError("BotFather не ответил в чате. Перезапусти Elys.")

    marker = max((m.id for m in await history()), default=0)
    try:
        await say("/cancel")  # Сбрасываем недооформленный прошлый диалог.
        await say("/newbot")
        await say(BOT_TITLE)
        found = TOKEN.search(await say(username))
        if not found:
            raise BotSetupError("BotFather не создал бота: username занят или отклонён. Перезапусти Elys.")
        return found[0]
    finally:
        try:
            await client.send_message("BotFather", "/cancel")  # Если мастер застрял на шаге username.
            await asyncio.sleep(poll)
            ids = [m.id for m in await history() if m.id > marker]
            if ids:
                await client.delete_messages("BotFather", ids, revoke=True)
        except Exception:
            # Без текста исключения: оно может содержать данные чата.
            log.warning("Не удалось удалить переписку с BotFather — удали её вручную: в ней токен бота.",
                        extra={"no_telegram": True})


class BotFatherWebApp:
    ORIGIN = "https://webappinternal.telegram.org"
    PATH = "/botfather"

    def __init__(self, link):
        self.base = self.ORIGIN + self.PATH
        self._check_url(link, self.PATH)
        parts = urlsplit(link)
        values = {**parse_qs(parts.query), **parse_qs(parts.fragment)}.get("tgWebAppData", [])
        if len(values) != 1 or not values[0]:
            raise BotSetupError("Telegram не вернул авторизацию Web App BotFather. Перезапусти Elys.")
        self._init_data = values[0]
        self._opener = build_opener(HTTPCookieProcessor(CookieJar()), _NoRedirect())
        self._api = None

    def _check_url(self, url, path):
        try:
            parts, origin = urlsplit(url), urlsplit(self.ORIGIN)
            valid = (parts.scheme == origin.scheme and parts.netloc == origin.netloc
                     and parts.path.rstrip("/") == path and not parts.username and not parts.password)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise BotSetupError("Неожиданный адрес Web App BotFather. Настройка остановлена.")

    def _read(self, url, data=None, *, bootstrap=False):
        self._check_url(url, self.PATH + "/api" if data is not None else urlsplit(url).path.rstrip("/"))
        request = Request(url, data=data, headers={
            "User-Agent": "Elys", "Origin": self.ORIGIN, "Referer": self.base,
        })
        try:
            try:
                response = self._opener.open(request, timeout=20)
            except HTTPError as error:
                # Без cookies стартовая страница отдаёт HTTP 400 с bootstrap для auth.
                if not bootstrap or error.code != 400:
                    error.close()
                    raise BotSetupError("Web App BotFather отклонил запрос. Перезапусти Elys.") from None
                response = error
            with response:
                body = response.read(_LIMIT + 1)
            if len(body) > _LIMIT:
                raise BotSetupError("Слишком большой ответ Web App BotFather. Настройка остановлена.")
            return body.decode("utf-8")
        except (OSError, URLError, UnicodeError, ValueError):
            # Не включаем URL, initData, cookies, ответ сервера или токен в исключение.
            raise BotSetupError("Не удалось связаться с Web App BotFather. Проверь сеть и перезапусти Elys.") from None

    def _request(self, method, **values):
        if self._api is None:
            raise BotSetupError("Нет авторизации Web App BotFather.")
        reply = self._read(self._api, urlencode({**values, "method": method}).encode())
        try:
            result = json.loads(reply)
        except (TypeError, ValueError):
            raise BotSetupError("Неизвестный ответ Web App BotFather. Настройка остановлена.") from None
        if not isinstance(result, dict) or result.get("error") or not result.get("ok"):
            raise BotSetupError("BotFather не подтвердил действие. Проверь ограничения в его Web App "
                                "и перезапусти Elys.")
        return result

    async def authenticate(self):
        await asyncio.to_thread(self._authenticate)

    def _authenticate(self):
        bootstrap = self._read(self.base, bootstrap=True)
        match = _API_URL.search(bootstrap)
        if not match:
            raise BotSetupError("Изменился интерфейс Web App BotFather. Нужна обновлённая версия Elys.")
        try:
            endpoint = urlsplit(urljoin(self.base, json.loads(match[1])))
        except ValueError:
            raise BotSetupError("Неизвестный адрес API Web App BotFather.") from None
        # TWebApp.init('/botfather') добавляет basePath к общему /api bootstrap.
        self._check_url(endpoint.geturl(), endpoint.path if endpoint.path == "/api" else self.PATH + "/api")
        self._api = self.base + "/api" + ("?" + endpoint.query if endpoint.query else "")
        try:
            result = self._request("auth", _auth=self._init_data)
            if result.get("api_url"):
                if not isinstance(result["api_url"], str):
                    raise BotSetupError("Неизвестный адрес API Web App BotFather.")
                api = urljoin(self.base, result["api_url"])
                self._check_url(api, self.PATH + "/api")
                self._api = api
        finally:
            self._init_data = None

    async def bots(self):
        # Все боты владельца: {username в нижнем регистре: (id, название)}.
        page = _Page()
        page.feed(await asyncio.to_thread(self._read, self.base))
        return {name: (identity, page.titles.get(name, "")) for name, identity in page.bots.items()}

    async def find_bot(self, username):
        found = (await self.bots()).get(username.lower())
        return found[0] if found else None

    async def create_bot(self, username):
        result = await asyncio.to_thread(self._request, "createBot", title=BOT_TITLE,
                                         about="", username=username, userpic="")
        try:
            identity = int(result["bot_id"])
            if identity <= 0:
                raise ValueError
            return identity
        except (KeyError, TypeError, ValueError):
            raise BotSetupError("BotFather не вернул ID созданного бота. Перезапусти Elys.") from None

    async def token(self, identity):
        page = _Page()
        page.feed(await asyncio.to_thread(self._read, f"{self.base}/bot/{identity}"))
        for token in TOKEN.findall("".join(page.tokens)):
            if int(token.split(":", 1)[0]) == identity:
                return token
        raise BotSetupError("Web App BotFather не вернул токен бота-помощника. Перезапусти Elys.")

    async def enable_inline(self, identity):
        await asyncio.to_thread(self._request, "changeSettings", bid=identity, **{"settings[inline]": "1"})
        await asyncio.to_thread(self._request, "changeSettings", bid=identity,
                                **{"settings[inph]": "Elys: команды и настройки"})
        # Inline Feedback 100%: бот получает inline_message_id отправленной формы и может её править.
        # В списке Web App 1 = 100%, 1000 = 0.1%.
        await asyncio.to_thread(self._request, "changeSettings", bid=identity, **{"settings[infdb]": "1"})
