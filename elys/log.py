"""логи: в терминал — коротко и по-русски, в файл — всё, с трейсбеками."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar

FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class ConsoleFormatter(logging.Formatter):
    MARKS: ClassVar[dict[int, str]] = {logging.WARNING: "⚠️  ", logging.ERROR: "❌ ", logging.CRITICAL: "❌ "}

    def __init__(self, file: Path) -> None:
        super().__init__()
        self.file = file

    def format(self, record: logging.LogRecord) -> str:
        text = f"{self.formatTime(record, '%H:%M:%S')}  {self.MARKS.get(record.levelno, '')}{record.getMessage()}"
        if record.exc_info:
            text += f" (подробности в {self.file})"  # трейсбек пугает, он в файле
        return text


def setup(level: str | int, file: Path) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter(file))
    rotating = RotatingFileHandler(file, maxBytes=5 << 20, backupCount=3, encoding="utf-8")
    rotating.setFormatter(logging.Formatter(FILE_FORMAT, "%Y-%m-%d %H:%M:%S"))

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.addHandler(console)
    root.addHandler(rotating)
    root.setLevel(level)
    # wzgram на INFO пишет каждое переподключение
    logging.getLogger("pyrogram").setLevel(max(root.level, logging.WARNING))
