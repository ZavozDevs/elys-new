import os
import pty
import subprocess
import sys
import textwrap

import pytest

from elys import term
from elys.term import BACKSPACE, CLEAR, DOWN, ENTER, ESC, INTERRUPT, UP, Field


@pytest.mark.parametrize(
    ("data", "keys", "rest"),
    [
        ("ab", ["a", "b"], ""),
        ("\x1b[A\x1b[B", [UP, DOWN], ""),
        ("\x1bOA", [UP], ""),
        ("\x1b[1;5C", [""], ""),  # неизвестная — игнорируется вызывающим
        ("x\x1b[", ["x"], "\x1b["),  # хвост дочитается следующим read
        ("\x1b", [], "\x1b"),
        ("\x1bq", [ESC, "q"], ""),
        ("\r\n\x7f\x08\x15\x03\x04", [ENTER, ENTER, BACKSPACE, BACKSPACE, CLEAR, INTERRUPT, INTERRUPT], ""),
        ("\x01ж", ["ж"], ""),
    ],
)
def test_split_keys(data, keys, rest):
    assert term.split_keys(data) == (keys, rest)


def feed(field, keys):
    return any(field.feed(key) for key in keys)  # any останавливается на первом True


def test_field_keeps_input_and_shows_error_until_valid():
    field = Field("Код", lambda t: t if t.isdecimal() else None, "только цифры")
    assert not feed(field, ["1", "a", ENTER])
    assert field.error == "только цифры" and field.buf == "1a"
    assert feed(field, [BACKSPACE, "2", ENTER])
    assert (field.value, field.error) == ("12", "")


def test_field_clear_default_secret_interrupt():
    field = Field("x", default="7")
    assert feed(field, ["1", CLEAR, ENTER]) and field.value == "7"
    secret = Field("p", secret=True)
    feed(secret, list(" pw "))
    assert "pw" not in secret.line()
    assert feed(secret, [ENTER]) and secret.value == " pw "  # пароль не обрезаем
    with pytest.raises(KeyboardInterrupt):
        Field("x").feed(INTERRUPT)
    empty = Field("x")
    assert not feed(empty, [ENTER]) and empty.error


def test_plain_field_shows_server_error_and_retries(monkeypatch, capsys):
    answers = iter(["+7999", "+79991234567"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    value = term.ask("Номер", lambda t: t if len(t) > 6 else None, "короткий", error="Telegram не знает номер")
    assert value == "+79991234567"
    out = capsys.readouterr().out
    assert out.index("Telegram не знает номер") < out.index("короткий")


def test_plain_choose(monkeypatch, capsys):
    answers = iter(["5", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert term.choose("Как?", [("A", "a"), ("B", "b")], default=1) == 1
    assert "от 1 до 2" in capsys.readouterr().out


def test_eof_is_interrupt(monkeypatch):
    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    with pytest.raises(KeyboardInterrupt):
        term.ask("x")


def test_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert term.paint("x", "ok") == "x"
    assert term.paint("x", "ok", color=True) == "\x1b[1;32mx\x1b[0m"


def test_qr_lines_halve_height_and_invert_without_color():
    matrix = [[True, False], [True, True], [False, False]]
    colored = term.qr_lines(matrix, color=True, indent=0)
    assert len(colored) == 2
    assert colored[0] == "\x1b[30;107m█▄\x1b[0m"
    assert term.qr_lines(matrix, color=False, indent=0) == [" ▀", "██"]


# настоящий терминал: pty, raw-режим, стрелки


SCRIPT = textwrap.dedent(
    """
    import asyncio, sys
    from elys import term
    i = term.choose("Как войти?", [("По QR-коду", "камера"), ("По номеру", "код")])
    v = asyncio.run(term.aask("Код", lambda t: t if t.isdecimal() else None, "только цифры"))
    print("RESULT", i, v)
    """
)


def run_in_pty(*steps: tuple[bytes, bytes]) -> str:
    # steps: (дождаться этого в выводе, потом нажать это).
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-c", SCRIPT],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": "xterm-256color"},
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    )
    os.close(slave)
    output = b""

    def read_until(marker: bytes) -> None:
        nonlocal output
        while marker not in output:
            output += os.read(master, 4096)

    for marker, keys in steps:
        read_until(marker)
        os.write(master, keys)
    try:
        while chunk := os.read(master, 4096):
            output += chunk
    except OSError:  # linux: EIO, когда процесс закрыл терминал
        pass
    proc.wait(timeout=10)
    os.close(master)
    return output.decode()


@pytest.mark.skipif(os.name != "posix", reason="pty только на posix")
def test_real_terminal_arrows_and_inline_error():
    # ↓ Enter → «По номеру»; «1a» Enter → ошибка под полем; ⌫ «2» Enter → принято
    out = run_in_pty(
        (b"Enter)", b"\x1b[B\r"),
        ("Код".encode(), b"1a\r"),
        ("только цифры".encode(), b"\x7f2\r"),
    )
    assert "RESULT 1 12" in out
    assert "только цифры" in out
    assert "\x1b[?25h" in out  # курсор вернули


@pytest.mark.skipif(os.name != "posix", reason="pty только на posix")
def test_real_terminal_ctrl_c_restores_terminal():
    out = run_in_pty((b"Enter)", b"\x03"))
    assert "KeyboardInterrupt" in out
    assert "\x1b[?25h" in out
