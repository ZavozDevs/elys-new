# логи: в терминал — коротко, ровными колонками, по-русски; в файл — всё, с трейсбеками.
#
#  00:36:41  ✓  Elys 0.1.0 запущен · Иван Петров
#  00:37:02  ▸  .ping             в «Работа»                 84 мс
#  00:37:15  ✗  Weather     команда .w сломалась · ошибка #a1f3, подробности в data/elys.log
#
# значок берётся из уровня или из extra={"mark": "ok" | "cmd"}.

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar

from elys import term
from elys.storage.files import private_directory, private_file, protect_existing

FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s%(error_tag)s: %(message)s"
MODULE_PREFIX = "elys.mod."
SOURCE_WIDTH = 10

_console: logging.Handler | None = None


def new_error_id() -> str:
    return os.urandom(2).hex()


class ErrorId(logging.Filter):
    # один номер ошибки на запись — и в терминале, и в файле (запись у обработчиков общая).

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and not getattr(record, "error_id", None):
            record.error_id = new_error_id()
        error_id = getattr(record, "error_id", None)
        record.error_tag = f" #{error_id}" if error_id else ""
        return True


class ConsoleFormatter(logging.Formatter):
    MARKS: ClassVar[dict[str, tuple[str, str]]] = {
        "info": ("·", "dim"),
        "ok": ("✓", "ok"),
        "cmd": ("▸", "accent"),
        "warn": ("⚠", "warn"),
        "err": ("✗", "err"),
    }

    def __init__(self, file: Path, *, color: bool | None = None) -> None:
        super().__init__()
        self.file = file
        self.color = term.colors_enabled() if color is None else color

    def _paint(self, text: str, style: str) -> str:
        return term.paint(text, style, color=self.color)

    def format(self, record: logging.LogRecord) -> str:
        mark = getattr(record, "mark", None)
        if mark not in self.MARKS:
            mark = "err" if record.levelno >= logging.ERROR else "warn" if record.levelno >= logging.WARNING else "info"
        symbol, style = self.MARKS[mark]
        time = self.formatTime(record, "%H:%M:%S")
        head = f" {self._paint(time, 'dim')}  {self._paint(symbol, style)}  "
        indent = len(time) + 6
        if record.name.startswith(MODULE_PREFIX):
            source = record.name[len(MODULE_PREFIX) :].ljust(SOURCE_WIDTH)
            head += self._paint(source, "bold") + "  "
            indent += len(source) + 2

        text = record.getMessage()
        error_id = getattr(record, "error_id", None)
        if record.exc_info or error_id:
            # трейсбек пугает — он в файле, здесь только номер, по которому его найти
            tag = f"ошибка #{error_id}, " if error_id else ""
            text += self._paint(f" · {tag}подробности в {self.file}", "dim")
        return head + text.replace("\n", "\n" + " " * indent)


class PrivateFileHandler(RotatingFileHandler):
    def _open(self):
        private_file(Path(self.baseFilename))
        return super()._open()


def setup(level: str | int, file: Path) -> None:
    global _console
    private_directory(file.parent)
    for backup in file.parent.glob(f"{file.name}.[123]"):
        protect_existing(backup)
    errors = ErrorId()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter(file))
    console.addFilter(errors)
    rotating = PrivateFileHandler(file, maxBytes=5 << 20, backupCount=3, encoding="utf-8")
    rotating.setFormatter(logging.Formatter(FILE_FORMAT, "%Y-%m-%d %H:%M:%S"))
    rotating.addFilter(errors)

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.addHandler(console)
    root.addHandler(rotating)
    root.setLevel(level)
    _console = console
    # wzgram на INFO пишет каждое переподключение
    logging.getLogger("pyrogram").setLevel(max(root.level, logging.WARNING))


@contextmanager
def quiet() -> Iterator[None]:
    # на время диалога в терминале — логи только в файл, чтобы не встревали в вопросы.
    console = _console
    if console is None:
        yield
        return
    level = console.level
    console.setLevel(logging.CRITICAL + 1)
    try:
        yield
    finally:
        console.setLevel(level)
