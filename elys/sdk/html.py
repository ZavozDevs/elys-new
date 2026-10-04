# аргументы всегда обычный текст: html экранируется в одном месте.

from html import escape as _escape
from urllib.parse import urlsplit

from elys.ui import emoji as icons

from .context import premium


def escape(text: object) -> str:
    return _escape(str(text), quote=True)


def b(text: object) -> str:
    return f"<b>{escape(text)}</b>"


def i(text: object) -> str:
    return f"<i>{escape(text)}</i>"


def code(text: object) -> str:
    return f"<code>{escape(text)}</code>"


def pre(text: object) -> str:
    return f"<pre>{escape(text)}</pre>"


def quote(text: object, *, expandable: bool = False) -> str:
    return f"<blockquote{' expandable' if expandable else ''}>{escape(text)}</blockquote>"


def link(text: object, url: str) -> str:
    if urlsplit(url).scheme not in {"https", "http", "tg", "mailto"}:
        raise ValueError("нужна ссылка https, http, tg или mailto")
    return f'<a href="{escape(url)}">{escape(text)}</a>'


def emoji(identity: str, fallback: str) -> str:
    return icons.emoji(identity, fallback, premium())


class Emojis:
    def __getitem__(self, name: str) -> str:
        return icons.render("{e:" + name + "}", premium())

    def __getattr__(self, name: str) -> str:
        return self[name]


E = Emojis()
