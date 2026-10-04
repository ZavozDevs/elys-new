import ast
import html
import inspect
import io
import linecache
import traceback
from typing import Any

import pyrogram
from pyrogram import Client, enums, filters, raw, types
from pyrogram.types import Message

from elys import Module, UserError, get_reply, raw_args, respond

module = Module("Eval")

FILENAME = "<eval>"
LIMIT = 4000  # лимит текста telegram 4096, с запасом на заголовки


@module.command("e", aliases=["eval"])
async def evaluate(client: Client, message: Message) -> None:
    # <код> — выполнить python, await можно на верхнем уровне
    source = raw_args(message)
    if not source:
        raise UserError("Напиши код после команды, например: 2 + 2")

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

    # лимит — по тексту после разбора HTML, не по длине &lt; и других entities.
    code = _truncate(source, 1000)
    room = LIMIT - len(code.encode("utf-16-le")) // 2
    body = _truncate(body.strip() or "None", room)
    await respond(
        message,
        f'<pre language="python">{html.escape(code)}</pre>\n{"✅" if ok else "🚫"} <pre>{html.escape(body)}</pre>',
    )


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
