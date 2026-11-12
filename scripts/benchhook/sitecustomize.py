"""Хук бенчмарка. Активен только если задан ELYS_BENCH_OUT и каталог в PYTHONPATH.

Считает на уровне сетевой сессии (одинаково для pyrogram и telethon):
  rpc     — все запросы к Telegram (с разбивкой по методам);
  foreign — входящие чужие сообщения (UpdateNew[Channel]Message, не out).
"""

import collections
import importlib.abc
import importlib.util
import inspect
import json
import os
import sys
import threading
import time

OUT = os.environ.get("ELYS_BENCH_OUT")
S = {"rpc": 0, "foreign": 0, "methods": collections.Counter()}
NEW = {"UpdateNewMessage", "UpdateNewChannelMessage"}


def _count_rpc(req):
    S["rpc"] += 1
    S["methods"][type(getattr(req, "query", req)).__name__] += 1


def _count_updates(u):
    items = getattr(u, "updates", None) or [u]
    for x in items:
        if type(x).__name__ in NEW and not getattr(getattr(x, "message", None), "out", True):
            S["foreign"] += 1


def _wrap(cls, name, before):
    orig = getattr(cls, name)
    if inspect.iscoroutinefunction(orig):

        async def w(self, arg, *a, **k):
            before(arg)
            return await orig(self, arg, *a, **k)
    else:

        def w(self, arg, *a, **k):
            before(arg)
            return orig(self, arg, *a, **k)

    setattr(cls, name, w)


TARGETS = {
    "pyrogram.session.session": [("Session", "invoke", _count_rpc)],
    "pyrogram.client": [("Client", "handle_updates", _count_updates)],
    "elystl.network.mtprotosender": [("MTProtoSender", "send", _count_rpc)],
    "elystl.client.updates": [("UpdateMethods", "_dispatch_update", _count_updates)],
}


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name not in TARGETS:
            return None
        sys.meta_path.remove(self)
        try:
            spec = importlib.util.find_spec(name)
        finally:
            sys.meta_path.insert(0, self)
        exec_orig = spec.loader.exec_module

        def exec_module(m):
            exec_orig(m)
            for cls, meth, fn in TARGETS[name]:
                _wrap(getattr(m, cls), meth, fn)

        spec.loader.exec_module = exec_module
        return spec


def _dump():
    while True:
        time.sleep(0.5)
        data = {"rpc": S["rpc"], "foreign": S["foreign"], "methods": dict(S["methods"])}
        with open(OUT + ".tmp", "w") as f:
            json.dump(data, f)
        os.replace(OUT + ".tmp", OUT)


if OUT:
    sys.meta_path.insert(0, _Finder())
    threading.Thread(target=_dump, daemon=True, name="bench-dump").start()


def _trace():
    """ELYS_BENCH_TRACE=1: раз в 5 мин пишет в OUT.trace, какие строки выросли с 90-й секунды."""
    import tracemalloc

    time.sleep(90)
    base = tracemalloc.take_snapshot()
    while True:
        time.sleep(300)
        snap = tracemalloc.take_snapshot()
        with open(OUT + ".trace", "a") as f:
            cur, peak = tracemalloc.get_traced_memory()
            f.write(f"=== {time.strftime('%H:%M:%S')} traced={cur >> 20}MB peak={peak >> 20}MB\n")
            for st in snap.compare_to(base, "lineno")[:15]:
                f.write(f"{st}\n")
            for st in snap.compare_to(base, "traceback")[:3]:
                f.write(f"--- {st.size_diff >> 10} KiB, {st.count_diff} blocks\n")
                f.write("\n".join(st.traceback.format(limit=12)) + "\n")


if OUT and os.environ.get("ELYS_BENCH_TRACE"):
    import tracemalloc

    tracemalloc.start(12)
    threading.Thread(target=_trace, daemon=True, name="bench-trace").start()
