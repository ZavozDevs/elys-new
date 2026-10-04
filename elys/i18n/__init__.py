# сначала эмодзи шаблона, потом аргументы; пользовательский текст не рендерится.

from functools import lru_cache
from html import escape
from pathlib import Path

import yaml

from elys.ui.emoji import render


def translate(strings, key: str, *, language: str = "ru", premium: bool = False, **values) -> str:
    template = next((strings[lang][key] for lang in dict.fromkeys((language, "ru", "en"))
                     if key in strings.get(lang, {})), key)
    return render(template, premium).format(**{k: escape(str(v)) for k, v in values.items()})


@lru_cache(maxsize=1)
def locales():
    return {p.stem: yaml.safe_load(p.read_text("utf-8"))
            for p in Path(__file__).with_name("locales").glob("*.yml")}


def t(key: str, *, language: str = "ru", premium: bool = False, **values) -> str:
    return translate(locales(), key, language=language, premium=premium, **values)
