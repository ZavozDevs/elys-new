# терминал без зависимостей: цвета, вопросы, меню стрелками, qr полублоками.
#
# termios/select/getpass импортируются только когда что-то спрашиваем — обычный запуск их не грузит.

from __future__ import annotations

import asyncio
import codecs
import os
import sys
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, TypeVar

T = TypeVar("T")
Parse = Callable[[str], Any]

_STYLES = {
    "bold": "1",
    "dim": "2",
    "accent": "1;38;5;141",
    "ok": "1;32",
    "warn": "1;33",
    "err": "1;31",
    "link": "4;38;5;141",
}


def colors_enabled(stream: Any = None) -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    stream = sys.stdout if stream is None else stream
    return bool(getattr(stream, "isatty", None) and stream.isatty())


def paint(text: str, style: str, *, color: bool | None = None) -> str:
    if color is None:
        color = colors_enabled()
    return f"\x1b[{_STYLES[style]}m{text}\x1b[0m" if color else text


# вывод


def write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def say(text: str = "") -> None:
    write(text + "\n")


def header(title: str) -> None:
    say()
    say(f"  {paint('✦', 'accent')} {paint('Elys', 'bold')} {paint('· ' + title, 'dim')}")
    say()


def ok(text: str) -> None:
    say(f"  {paint('✓', 'ok')} {text}")


def error(text: str) -> None:
    say(f"  {paint('✗', 'err')} {text}")


def hint(text: str) -> None:
    say(paint(f"  {text}", "dim"))


def steps(items: Sequence[str]) -> None:
    for i, item in enumerate(items, 1):
        say(f"    {paint(f'{i}.', 'accent')} {item}")
    say()


# клавиши

UP, DOWN, ENTER, BACKSPACE, CLEAR, INTERRUPT, ESC = "up", "down", "enter", "backspace", "clear", "interrupt", "esc"
_CSI_KEYS = {"A": UP, "B": DOWN}
_CONTROL = {
    "\r": ENTER,
    "\n": ENTER,
    "\x7f": BACKSPACE,
    "\x08": BACKSPACE,
    "\x15": CLEAR,  # ctrl+u
    "\x03": INTERRUPT,  # ctrl+c
    "\x04": INTERRUPT,  # ctrl+d
}


def split_keys(data: str) -> tuple[list[str], str]:
    # разбирает ввод на клавиши; возвращает (клавиши, недочитанный хвост escape-последовательности).
    #
    # печатный символ — сам символ, особые клавиши — имена из констант выше, неизвестное — "".
    keys: list[str] = []
    i = 0
    while i < len(data):
        ch = data[i]
        if ch == "\x1b":
            if i + 1 >= len(data):
                break
            if data[i + 1] in "[O":
                j = i + 2
                while j < len(data) and not "@" <= data[j] <= "~":
                    j += 1
                if j >= len(data):
                    break
                keys.append(_CSI_KEYS.get(data[j], ""))
                i = j + 1
                continue
            keys.append(ESC)
            i += 1
            continue
        if ch in _CONTROL:
            keys.append(_CONTROL[ch])
        elif ch >= " ":
            keys.append(ch)
        i += 1
    return keys, data[i:]


class _Reader:
    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.rest = ""
        self.queue: list[str] = []

    def key(self) -> str:
        import select

        while not self.queue:
            if self.rest and not select.select([self.fd], [], [], 0.05)[0]:
                self.rest = ""  # одиночный esc
                return ESC
            chunk = os.read(self.fd, 256)
            if not chunk:
                return INTERRUPT
            keys, self.rest = split_keys(self.rest + self.decoder.decode(chunk))
            self.queue.extend(k for k in keys if k)
        return self.queue.pop(0)


def interactive() -> bool:
    # Возможность перерисовки и посимвольного ввода, а не наличие ввода вообще:
    # панели могут передавать строки через pipe без TTY.
    if os.name != "posix" or os.environ.get("TERM") == "dumb":
        return False
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        import termios
    except ImportError:
        return False
    try:
        termios.tcgetattr(sys.stdin.fileno())
    except (OSError, ValueError, termios.error):
        return False
    return True


@contextmanager
def _raw(fd: int) -> Iterator[None]:
    # посимвольно, без эха; Ctrl+C приходит как \x03 (ISIG выкл) — так поток ввода завершается сам.
    # opost не трогаем: \n по-прежнему переводит строку.
    import termios

    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG | termios.IEXTEN)
    new[0] &= ~termios.IXON
    new[6][termios.VMIN] = 1
    new[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSADRAIN, new)
    try:
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# поле ввода


class Field:
    # состояние поля: буфер, ошибка под полем, результат. рисование — снаружи.

    def __init__(
        self,
        label: str,
        parse: Parse | None = None,
        hint: str = "",
        *,
        secret: bool = False,
        placeholder: str = "",
        initial: str = "",
        error: str = "",
        default: str | None = None,
    ) -> None:
        self.label = label
        self.parse = parse
        self.hint = hint or "это поле нельзя оставить пустым"
        self.secret = secret
        self.placeholder = placeholder
        self.buf = initial
        self.error = error
        self.default = default
        self.value: Any = None

    def feed(self, key: str) -> bool:
        # true — ввод принят, значение в self.value.
        if key == INTERRUPT:
            raise KeyboardInterrupt
        if key == ENTER:
            text = (self.buf if self.secret else self.buf.strip()) or (self.default or "")
            value = self.parse(text) if self.parse else (text or None)
            if value is None:
                self.error = self.hint
                return False
            self.value, self.error = value, ""
            return True
        if key == BACKSPACE:
            self.buf = self.buf[:-1]
        elif key == CLEAR:
            self.buf = ""
        elif len(key) == 1:
            self.buf += key
        return False

    def line(self, *, done: bool = False) -> str:
        shown = "*" * len(self.buf) if self.secret else self.buf
        if done and not self.buf and self.default:
            shown = self.default
        if not shown and not done:
            if self.placeholder:
                shown = paint(self.placeholder, "dim")
            elif self.default:
                shown = paint(self.default, "dim")
        return f"{paint('?', 'accent')} {paint(self.label, 'bold')}  {shown}"

    def error_line(self) -> str:
        return f"  {paint('✗', 'err')} {self.error}"


def _field_tty(field: Field, again: bool) -> Any:
    fd = sys.stdin.fileno()
    reserved = False  # строка под полем уже есть — дальше ходим по ней без прокрутки
    if again:
        write("\x1b[1A\r\x1b[2K")  # повтор после ошибки от telegram — на месте прошлой попытки

    def render(done: bool = False) -> None:
        nonlocal reserved
        out = ""
        if field.error and not reserved:
            out, reserved = "\n\x1b[1A", True
        out += "\r\x1b[2K" + field.line(done=done)
        if reserved:
            below = "" if done or not field.error else field.error_line()
            out += "\x1b7\x1b[1B\r\x1b[2K" + below + "\x1b8"
        write(out)

    try:
        with _raw(fd):
            reader = _Reader(fd)
            render()
            while not field.feed(reader.key()):
                render()
    except KeyboardInterrupt:
        field.error = ""
        render(done=True)
        write("\n")
        raise
    render(done=True)
    write("\n")
    return field.value


def _field_plain(field: Field) -> Any:
    label = f"{paint('?', 'accent')} {paint(field.label, 'bold')}"
    if field.placeholder:
        label += paint(f" ({field.placeholder})", "dim")
    if field.default:
        label += paint(f" [{field.default}]", "dim")
    label += ": "
    if field.secret and not sys.stdin.isatty():
        hint("В этой консоли пароль может быть виден и сохранён в журнале панели.")
        hint("Если к ней есть доступ у других людей, нажми Ctrl+C и выполни вход в личном терминале.")
    while True:
        if field.error:
            say(field.error_line())
        if field.secret and sys.stdin.isatty():
            from getpass import getpass

            field.buf = getpass(label)
        else:
            field.buf = input(label)
        if field.feed(ENTER):
            return field.value


def ask(label: str, parse: Parse | None = None, hint: str = "", *, again: bool = False, **kwargs: Any) -> Any:
    # спросить значение; parse возвращает None для неподходящего — тогда hint под полем и ещё раз.
    #
    # again=True — повтор того же поля сразу после него (ошибка от telegram): рисуем поверх прошлой попытки.
    field = Field(label, parse, hint, **kwargs)
    return _field_tty(field, again) if interactive() else _field_plain(field)


# меню


def choose(question: str, options: Sequence[tuple[str, str]], default: int = 0) -> int:
    # выбор стрелками (или цифрой); без tty — список с номерами.
    if not interactive():
        return _choose_plain(question, options, default)
    n = len(options)
    width = max(len(title) for title, _ in options)
    selected = default
    digits = "123456789"[:n]

    def option(i: int) -> str:
        title, note = options[i]
        label = f"{i + 1}. {title.ljust(width)}"
        if i == selected:
            return f" {paint('❯', 'accent')} {paint(label, 'accent')}   {paint(note, 'dim')}"
        return f"   {label}   {paint(note, 'dim')}"

    say(f"{paint('?', 'accent')} {paint(question, 'bold')}  {paint('(↑↓ или цифра, затем Enter)', 'dim')}")
    up = f"\x1b[{n - 1}A" if n > 1 else ""
    fd = sys.stdin.fileno()
    write("\x1b[?25l")
    try:
        with _raw(fd):
            reader = _Reader(fd)
            while True:
                write("\r" + "\n".join("\x1b[2K" + option(i) for i in range(n)))
                key = reader.key()
                if key == ENTER:
                    break
                if key in digits:
                    selected = digits.index(key)
                if key == INTERRUPT:
                    raise KeyboardInterrupt
                if key == UP:
                    selected = (selected - 1) % n
                elif key == DOWN:
                    selected = (selected + 1) % n
                write(up)
    finally:
        # меню сворачивается в одну строку с ответом
        write("\r" + up + "\x1b[1A\x1b[J\x1b[?25h")
    say(f"{paint('?', 'accent')} {paint(question, 'bold')} {paint(options[selected][0], 'accent')}")
    return selected


def _choose_plain(question: str, options: Sequence[tuple[str, str]], default: int) -> int:
    n = len(options)
    width = max(len(title) for title, _ in options)
    say(f"{paint('?', 'accent')} {paint(question, 'bold')}")
    for i, (title, note) in enumerate(options, 1):
        say(f"  {paint(str(i), 'accent')}  {title.ljust(width)}   {paint(note, 'dim')}")

    def parse(text: str) -> int | None:
        return int(text) - 1 if text.isdecimal() and 1 <= int(text) <= n else None

    hint("Введи номер и нажми Enter.")
    return ask("Номер", parse, f"введи число от 1 до {n}", default=str(default + 1))


# async-обёртки: ввод в своём потоке, как pyrogram.utils.ainput


async def _in_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    executor = ThreadPoolExecutor(1, thread_name_prefix="elys-input")
    try:
        return await asyncio.get_running_loop().run_in_executor(executor, lambda: func(*args, **kwargs))
    finally:
        executor.shutdown(wait=False)


async def aask(label: str, parse: Parse | None = None, hint: str = "", **kwargs: Any) -> Any:
    return await _in_thread(ask, label, parse, hint, **kwargs)


async def achoose(question: str, options: Sequence[tuple[str, str]], default: int = 0) -> int:
    return await _in_thread(choose, question, options, default)


# перерисовываемый блок (qr)


class Area:
    def __init__(self) -> None:
        self.lines = 0

    def draw(self, lines: Sequence[str]) -> None:
        self.clear()
        for line in lines:
            say(line)
        self.lines = len(lines)

    def clear(self) -> None:
        if self.lines and interactive():
            write(f"\x1b[{self.lines}F\x1b[J")
        self.lines = 0


def qr_lines(matrix: Sequence[Sequence[bool]], *, color: bool | None = None, indent: int = 4) -> list[str]:
    # qr полублоками: две строки модулей в одной строке терминала.
    if color is None:
        color = colors_enabled()
    rows = [list(row) for row in matrix]
    if len(rows) % 2:
        rows.append([False] * len(rows[0]))
    pad = " " * indent
    lines = []
    for top, bottom in zip(rows[::2], rows[1::2], strict=True):
        if color:
            # тёмные модули на белом фоне — читается на любой теме терминала
            line = "".join(
                "█" if t and b else "▀" if t else "▄" if b else " " for t, b in zip(top, bottom, strict=True)
            )
            lines.append(f"{pad}\x1b[30;107m{line}\x1b[0m")
        else:
            # без цвета фон терминала обычно тёмный: рисуем светлые модули
            line = "".join(
                " " if t and b else "▄" if t else "▀" if b else "█" for t, b in zip(top, bottom, strict=True)
            )
            lines.append(pad + line)
    return lines
