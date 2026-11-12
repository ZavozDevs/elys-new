# rich → обычный HTML Telegram: тот же ответ без Premium и в режиме «off» (§12.6).
# Как текст самого rich-сообщения (message.text): без подписей <summary> и шапок таблиц, строка за строкой;
# <details> → закрытая цитата, заголовок → «эмодзи <b>текст</b>».

import re

_KEEP = "b|i|u|s|a|code|pre|blockquote|tg-emoji|tg-spoiler"
_RULES = [
    (re.compile(pattern, re.S), replace)
    for pattern, replace in (
        (r"<h\d[^>]*>\s*(\{e:\w+\}\s*)?(.*?)</h\d>", lambda m: f"{m[1] or ''}<b>{re.sub(r'</?code>', '', m[2])}</b>\n"),
        (r"<details[^>]*>\s*<summary>.*?</summary>(.*?)</details>", r"<blockquote expandable>\1</blockquote>\n"),
        (r"<footer>(.*?)</footer>", r"<i>\1</i>"),
        (r"<tr>\s*<th.*?</tr>", ""),  # шапка таблицы
        (r"</td>\s*<td[^>]*>", " — "),  # ячейки строки
        (r"</tr>|</p>|<br\s*/?>", "\n"),
        (rf"</?(?!(?:{_KEEP})\b)[a-z][^>]*>", ""),  # прочие rich-теги
        (r"(<blockquote[^>]*>)\s+|\s+(</blockquote>)", r"\1\2"),
        (r"\n\s*\n", "\n"),
    )
]


def plain(rich: str) -> str:
    for pattern, replace in _RULES:
        rich = pattern.sub(replace, rich)
    return rich.strip()
