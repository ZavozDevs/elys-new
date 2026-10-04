import logging
import re
import subprocess
import sys
from pathlib import Path

from elys import log


def record(name="elys.app", level=logging.INFO, msg="текст", exc=False, **extra):
    exc_info = None
    if exc:
        try:
            raise ValueError("x")
        except ValueError:
            exc_info = sys.exc_info()
    rec = logging.LogRecord(name, level, __file__, 1, msg, (), exc_info)
    rec.__dict__.update(extra)
    return rec


def fmt(rec):
    return log.ConsoleFormatter(Path("data/elys.log"), color=False).format(rec)


def test_marks_and_columns():
    assert re.fullmatch(r" \d\d:\d\d:\d\d  ·  текст", fmt(record()))
    assert "  ✓  " in fmt(record(mark="ok"))
    assert "  ▸  " in fmt(record(name="elys.cmd", mark="cmd"))
    assert "  ⚠  " in fmt(record(level=logging.WARNING))
    line = fmt(record(name="elys.mod.Weather", level=logging.ERROR))
    assert line.endswith("✗  Weather     текст")


def test_multiline_is_indented_under_text():
    first, second = fmt(record(name="elys.mod.Welcome", msg="раз\nдва")).split("\n")
    assert second.index("два") == first.index("раз")


def test_error_id_is_same_in_terminal_and_file(tmp_path):
    file = tmp_path / "elys.log"
    log.setup("INFO", file)
    try:
        console = logging.getLogger().handlers[0]
        lines = []
        console.emit = lambda rec: lines.append(console.format(rec))
        logging.getLogger("elys.mod.Weather").exception("упало", exc_info=ValueError("x"))
        logging.getLogger("elys.mod.Weather").error("с номером", extra={"error_id": "beef"})
    finally:
        for handler in logging.getLogger().handlers:
            handler.flush()
    error_id = re.search(r"ошибка #([0-9a-f]{4})", lines[0])[1]
    text = file.read_text()
    assert f"elys.mod.Weather #{error_id}: упало" in text
    assert "Traceback" in text or "ValueError" in text
    assert "Traceback" not in lines[0]
    assert "ошибка #beef" in lines[1] and "#beef: с номером" in text


def test_quiet_hides_console_only(tmp_path):
    file = tmp_path / "elys.log"
    log.setup("INFO", file)
    console = logging.getLogger().handlers[0]
    shown = []
    console.emit = lambda rec: shown.append(rec)
    with log.quiet():
        logging.getLogger("elys.app").info("тихо")
    logging.getLogger("elys.app").info("громко")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert [r.getMessage() for r in shown] == ["громко"]
    assert "тихо" in file.read_text()


def test_normal_start_does_not_load_wizard_stuff():
    # termios и pyrogram.qrlogin грузит сам wzgram при import pyrogram — проверяем только своё
    lazy = ("elys.wizard", "qrcode")
    code = f"import sys, elys.__main__, elys.app; print([m for m in {lazy!r} if m in sys.modules])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


def test_rotation_keeps_files_private(tmp_path):
    import os

    import pytest

    if os.name != "posix":
        pytest.skip("POSIX permissions")
    file = tmp_path / "elys.log"
    file.write_text("old\n")
    file.chmod(0o644)
    handler = log.PrivateFileHandler(file, maxBytes=10, backupCount=2, encoding="utf-8")
    try:
        handler.emit(record(msg="new log entry"))
        handler.emit(record(msg="another entry"))
    finally:
        handler.close()
    files = list(tmp_path.iterdir())
    assert {path.name for path in files} == {"elys.log", "elys.log.1", "elys.log.2"}
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in files)
