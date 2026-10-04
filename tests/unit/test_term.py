import io
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


def test_eof_is_reported_to_caller(monkeypatch):
    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    with pytest.raises(EOFError):
        term.ask("x")


def test_plain_secret_warns_and_preserves_whitespace(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(" pw \n"))
    assert term.ask("Пароль", secret=True) == " pw "
    out = capsys.readouterr().out
    assert "пароль может быть виден" in out
    assert "Ctrl+C" in out
    assert " pw " not in out


@pytest.mark.parametrize("dumb", [False, True])
def test_terminal_capability_fallback(monkeypatch, dumb):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "dumb" if dumb else "xterm")

    def no_fd():
        raise OSError("not a terminal")

    monkeypatch.setattr(sys.stdin, "fileno", no_fd)
    assert not term.interactive()


@pytest.mark.parametrize("tty", [False, True])
def test_area_does_not_move_cursor_without_terminal_support(monkeypatch, capsys, tty):
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
    area = term.Area()
    area.draw(["QR 1"])
    area.draw(["QR 2"])
    area.clear()
    assert capsys.readouterr().out == "QR 1\nQR 2\n"


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


@pytest.mark.parametrize("answer", ["2", "9\n2", ""])
def test_real_pipe_menu_and_async_field(answer):
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        input=f"{answer}\n1a\n12\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    selected = 0 if answer == "" else 1
    assert f"RESULT {selected} 12" in proc.stdout
    assert "По QR-коду" in proc.stdout and "По номеру" in proc.stdout
    assert "Введи номер и нажми Enter" in proc.stdout
    assert "только цифры" in proc.stdout
    assert "\x1b" not in proc.stdout


def test_real_pipe_eof_exits_without_hanging():
    proc = subprocess.run([sys.executable, "-c", SCRIPT], input="", capture_output=True, text=True, timeout=10)
    assert proc.returncode != 0
    assert "EOFError" in proc.stderr


def run_in_pty(*steps: tuple[bytes, bytes], terminal: str = "xterm-256color") -> str:
    # steps: (дождаться этого в выводе, потом нажать это).
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-c", SCRIPT],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": terminal},
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
@pytest.mark.parametrize("keys", [b"2\r", b"2\x1b[A\r"])
def test_real_terminal_numbers_can_be_confirmed_or_changed(keys):
    out = run_in_pty(
        (b"Enter)", keys),
        ("Код".encode(), b"42\r"),
    )
    selected = 0 if b"[A" in keys else 1
    assert f"RESULT {selected} 42" in out
    assert "1. По QR-коду" in out and "2. По номеру" in out
    assert "\x1b[?25h" in out


@pytest.mark.skipif(os.name != "posix", reason="pty только на posix")
def test_real_dumb_terminal_uses_numbered_menu():
    out = run_in_pty(
        ("Номер".encode(), b"2\n"),
        ("Код:".encode(), b"42\n"),
        terminal="dumb",
    )
    assert "RESULT 1 42" in out
    assert "\x1b" not in out


@pytest.mark.skipif(os.name != "posix", reason="pty только на posix")
def test_real_terminal_ctrl_c_restores_terminal():
    out = run_in_pty((b"Enter)", b"\x03"))
    assert "KeyboardInterrupt" in out
    assert "\x1b[?25h" in out
