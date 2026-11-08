# аргументы всегда обычный текст: html экранируется в одном месте.

from html import escape as _escape
from urllib.parse import urlsplit

from elys.i18n import Html
from elys.ui import emoji as icons

from .context import premium


def escape(text: object) -> Html:
    # готовый Html не экранируется повторно — помощники и t() составляются свободно
    return text if isinstance(text, Html) else Html(_escape(str(text), quote=True))


def b(text: object) -> Html:
    return Html(f"<b>{escape(text)}</b>")


def i(text: object) -> Html:
    return Html(f"<i>{escape(text)}</i>")


def code(text: object) -> Html:
    return Html(f"<code>{escape(text)}</code>")


def pre(text: object) -> Html:
    return Html(f"<pre>{escape(text)}</pre>")


def quote(text: object, *, expandable: bool = False) -> Html:
    return Html(f"<blockquote{' expandable' if expandable else ''}>{escape(text)}</blockquote>")


def link(text: object, url: str) -> Html:
    if urlsplit(url).scheme not in {"https", "http", "tg", "mailto"}:
        raise ValueError("нужна ссылка https, http, tg или mailto")
    return Html(f'<a href="{escape(url)}">{escape(text)}</a>')


def emoji(identity: str, fallback: str) -> Html:
    return Html(icons.emoji(identity, fallback, premium()))


class Emojis:
    def __getitem__(self, name: str) -> Html:
        return Html(icons.render("{e:" + name + "}", premium()))

    def __getattr__(self, name: str) -> Html:
        return self[name]


E = Emojis()
