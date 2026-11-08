"""Переводы: паки ``langs/<код>/<раздел>.yml`` отдельно от кода.

Поиск: язык → ru → en → сам ключ. Встроенные паки лежат рядом с кодом, ``data/langs``
их перекрывает, модуль-пакет приносит ``langs/<код>.yml`` в свой раздел.

Без ``str.format``: подставляются только ``{имя}`` и ``{n|форма|форма|форма}``, значения
экранируются, если это не ``Html``. Чужой перевод не достанет атрибуты объектов,
забытый аргумент не уронит команду.
"""

import logging
import re
from html import escape
from pathlib import Path

import yaml

from elys.ui.emoji import render

log = logging.getLogger("elys.i18n")
BUILTIN = Path(__file__).with_name("langs")
FALLBACK = ("ru", "en")
META = "_meta"
FIELD = re.compile(r"\{(\w+)(?:\|([^{}]*))?\}")
CODE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?")


class Html(str):
    """Готовый HTML: подставляется и экранируется как есть, без второго экранирования."""


def plural(language: str, n) -> int:
    # номер формы: ru/uk/be/pl — 1/2/5, остальные — 1/много
    n, base = abs(int(n)), language[:2]
    if base not in {"ru", "uk", "be", "pl"}:
        return int(n != 1)
    if (n == 1) if base == "pl" else (n % 10 == 1 and n % 100 != 11):
        return 0
    return 1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2


def fill(template: str, language: str, values: dict) -> Html:
    def substitute(match: re.Match) -> str:
        name, forms = match.groups()
        if name not in values:
            return match.group(0)
        value = values[name]
        if forms is not None and isinstance(value, int):
            options = forms.split("|")
            return options[min(plural(language, value), len(options) - 1)]
        return value if isinstance(value, Html) else escape(str(value))
    return Html(FIELD.sub(substitute, template))


def fields(template: str) -> set[str]:
    return {name for name, _ in FIELD.findall(template)}


def read(path: Path, *, meta: bool = False) -> dict:
    try:
        data = yaml.safe_load(path.read_text("utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        log.warning("не читается перевод %s: %s", path, error)
        return {}
    allowed = (str, int, float) if meta else str
    clean = {str(k): v for k, v in data.items() if isinstance(v, allowed)} if isinstance(data, dict) else {}
    if clean.keys() != (data.keys() if isinstance(data, dict) else {}.keys()):
        log.warning("в %s пропущены значения не строки", path)
    return clean


class Catalog:
    """Переводы приложения: язык → раздел → ключ → шаблон."""

    def __init__(self, *roots: Path) -> None:
        self.roots = [BUILTIN, *map(Path, roots)]
        self.attached: dict[str, Path] = {}
        self.reload()

    def reload(self) -> None:
        self._packs, self._missing = None, set()

    def attach(self, section: str, directory: Path) -> None:
        self.attached[section.lower()] = Path(directory)
        self.reload()

    def detach(self, section: str) -> None:
        if self.attached.pop(section.lower(), None):
            self.reload()

    @property
    def packs(self) -> dict:
        if self._packs is None:
            files = [(f.stem, s, f) for s, d in self.attached.items() for f in sorted(d.glob("*.yml"))]
            files += [(f.parent.name, f.stem, f) for root in self.roots for f in sorted(root.glob("*/*.yml"))]
            self._packs = {}
            for lang, section, file in files:
                if CODE.fullmatch(lang):
                    self._packs.setdefault(lang, {}).setdefault(section, {}).update(read(file, meta=section == META))
        return self._packs

    def languages(self) -> dict[str, dict]:
        # код → _meta; ru и en первыми
        found = {code: {"name": code, "flag": "", "version": 0} | s[META]
                 for code, s in self.packs.items() if META in s}
        # [*FALLBACK, code].index(code) — место в FALLBACK или «после всех» одним выражением
        return dict(sorted(found.items(), key=lambda i: ([*FALLBACK, i[0]].index(i[0]), i[1]["name"])))

    def t(self, key: str, *, language: str = "ru", premium: bool = False, sections=("core",),
          extra: dict | None = None, default: str | None = None, **values) -> str:
        for lang in dict.fromkeys((language, *FALLBACK)):
            for strings in ((extra or {}).get(lang, {}), *(self.packs.get(lang, {}).get(s, {}) for s in sections)):
                if key in strings:
                    return fill(render(strings[key], premium), lang, values)
        if default is not None:  # например doc настройки стороннего модуля — как есть
            return default
        if (language, key) not in self._missing:
            self._missing.add((language, key))
            log.warning("нет перевода %r (%s)", key, language)
        return fill(key, language, values)


catalog = Catalog()  # только встроенные паки; у App свой app.i18n с data/langs
