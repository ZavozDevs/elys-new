import ast
import html
import inspect
import io
import linecache
import traceback
from contextlib import suppress
from typing import Any

import pyrogram
from pyrogram import Client, enums, filters, raw, types
from pyrogram.types import Message

from elys import Module, UserError, get_reply, raw_args, respond

module = Module("Eval")

FILENAME = "<eval>"
LIMIT = 4000  # лимит текста telegram 4096, с запасом на заголовки
PAGE = 3800  # страница листалки: текст + номер страницы
PAGES = 10  # больше страниц листать неудобно — отдаём файлом


@module.command("e", aliases=["eval"], roles=("sudo",))
async def evaluate(client: Client, message: Message) -> None:
    # <код> — выполнить python, await можно на верхнем уровне
    source = raw_args(message)
    if not source:
        raise UserError(module.t("no_code"))

    out = io.StringIO()
    env = {
        "__name__": "__eval__",
        "__builtins__": __builtins__,
        "app": module.app,
        "c": client,
        "client": client,
        "m": message,
        "message": message,
        "r": await get_reply(message),
        "module": module,
        "pyrogram": pyrogram,
        "raw": raw,
        "types": types,
        "enums": enums,
        "filters": filters,
        "print": lambda *a, file=out, **kw: print(*a, file=file, **kw),  # без глобального redirect_stdout
    }
    try:
        result = await run(source, env)
    except (Exception, SystemExit) as e:  # exit() в коде не должен ронять бота
        body, ok = _traceback(e), False
    else:
        body, ok = out.getvalue() + ("" if result is None else _show(result)), True

    body = body.strip() or "None"
    mark = "✅" if ok else "🚫"
    code = _truncate(source, 1000)
    room = LIMIT - _units(code)

    # 1. влезает в одно сообщение — как раньше.
    if _units(body) <= room:
        await respond(message, _screen(code, mark, body))
        return

    # 2. длинный вывод — листалка через бота (до PAGES страниц).
    short = _truncate(source, 300)
    chunks = _split(body, PAGE - _units(short))
    if len(chunks) <= PAGES and await _paginate(message, short, mark, chunks):
        return

    # 3. бот недоступен или страниц слишком много — файлом.
    if await _send_file(client, message, short, mark, body):
        return

    # 4. совсем ничего не вышло — обрезаем, чтобы хоть что-то показать.
    await respond(message, _screen(code, mark, _truncate(body, room)))


def _screen(code: str, mark: str, body: str) -> str:
    return f'<pre language="python">{html.escape(code)}</pre>\n{mark} <pre>{html.escape(body)}</pre>'


async def _paginate(message: Message, code: str, mark: str, chunks: list[str]) -> bool:
    app = module.app
    if getattr(app, "inline", None) is None or getattr(app, "bot", None) is None:
        return False
    try:
        await module.list(message, [_screen(code, mark, chunk) for chunk in chunks])
    except Exception:
        module.log.warning("не удалось показать вывод листалкой, отправляю файлом", exc_info=True)
        return False
    await _drop(message)
    return True


async def _drop(message: Message) -> None:
    # ответ ушёл новым сообщением — убираем команду, но только свою.
    if message.outgoing:
        with suppress(Exception):
            await message.delete()


async def _send_file(client: Client, message: Message, code: str, mark: str, body: str) -> bool:
    data = body.encode("utf-8")
    document = io.BytesIO(data)
    document.name = "eval.txt"
    try:
        await client.send_document(
            message.chat.id,
            document,
            caption=f'<pre language="python">{html.escape(code)}</pre>\n'
            + module.t("in_file", mark=mark, size=_size(len(data))),
            message_thread_id=getattr(message, "message_thread_id", None),
            reply_to_message_id=getattr(message, "reply_to_message_id", None),
        )
    except Exception:
        module.log.warning("не удалось отправить вывод файлом", exc_info=True)
        return False
    await _drop(message)
    return True


async def run(source: str, env: dict[str, Any]) -> Any:
    # выполнить код; значение последнего выражения — результат.
    tree = ast.parse(source, FILENAME)
    last = tree.body[-1] if tree.body else None
    if isinstance(last, ast.Expr):
        tree.body[-1] = ast.copy_location(
            ast.Assign(targets=[ast.Name("__result__", ast.Store())], value=last.value), last
        )
        ast.fix_missing_locations(tree)
    code = compile(tree, FILENAME, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    linecache.cache[FILENAME] = (len(source), None, source.splitlines(True), FILENAME)  # строки в трейсбеке
    if code.co_flags & inspect.CO_COROUTINE:
        await eval(code, env)
    else:
        exec(code, env)
    return env.get("__result__")


def _units(text: str) -> int:
    # длина в utf-16 — так считает telegram.
    return len(text.encode("utf-16-le")) // 2


def _split(text: str, units: int) -> list[str]:
    # режем по строкам, длинную строку — по utf-16 без разрыва суррогатных пар.
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        while _units(line) > units:
            if current:
                chunks.append(current)
                current = ""
            head = line.encode("utf-16-le")[: units * 2].decode("utf-16-le", errors="ignore")
            chunks.append(head)
            line = line[len(head) :]
        if _units(current) + _units(line) > units:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return [chunk.rstrip("\n") or " " for chunk in chunks]


def _size(count: int) -> str:
    return module.t("bytes", n=count) if count < 1024 else module.t("kb", n=f"{count / 1024:.1f}")


def _truncate(text: str, units: int) -> str:
    encoded = text.encode("utf-16-le")
    if len(encoded) <= units * 2:
        return text
    return encoded[: (units - 1) * 2].decode("utf-16-le", errors="ignore") + "…"


def _show(value: Any) -> str:
    # объекты wzgram печатаются json-ом, остальное — repr
    return str(value) if isinstance(value, pyrogram.types.Object) else repr(value)


def _traceback(e: BaseException) -> str:
    tb = e.__traceback__
    while tb is not None and tb.tb_frame.f_code.co_filename != FILENAME:
        tb = tb.tb_next  # кадры eval-обвязки не показываем
    return "".join(traceback.format_exception(type(e), e, tb))
