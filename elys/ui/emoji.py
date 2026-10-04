# один реестр и один рендер для всех способов вставить эмодзи.

import re
from functools import lru_cache
from html import escape
from pathlib import Path

import yaml

# Заглушка inline-результата с премиум-эмодзи: Telegram вырезает custom_emoji из результатов,
# поэтому отправляем её, а затем правим сообщение полным текстом (премиум остаётся при правке).
PLACEHOLDER = "⭐"
TOKEN = re.compile(r"\{e:([\w]+)\}")


def _load():
    registry = {}
    data = yaml.safe_load(Path(__file__).with_name("emojis.yml").read_text("utf-8"))
    for group in data.values():
        for name, item in group.items():
            for alias in (name, *item.get("aliases", ())):
                if alias in registry:
                    raise ValueError(f"повтор эмодзи: {alias}")
                registry[alias] = (str(item["id"]), item["fallback"])
    return registry


REGISTRY = _load()


def emoji(identity: str, fallback: str, premium: bool) -> str:
    if not str(identity).isdecimal():
        raise ValueError("id эмодзи должен состоять из цифр")
    text = escape(fallback)
    return f'<tg-emoji emoji-id="{identity}">{text}</tg-emoji>' if premium else text


def unknown(text: str) -> set[str]:
    return set(TOKEN.findall(text)) - REGISTRY.keys()


@lru_cache(maxsize=1024)
def render(text: str, premium: bool = False) -> str:
    def replace(match):
        item = REGISTRY.get(match[1])
        return emoji(*item, premium) if item else "❔"

    return TOKEN.sub(replace, text)
