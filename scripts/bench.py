"""Бенчмарк Elys: RAM, старт, задержка .ping, RPC на 1000 чужих сообщений.

    python3 scripts/bench.py PLAN.json

Код бота не меняется: счётчики — в scripts/benchhook (подключается через PYTHONPATH),
.ping шлёт bench_drive.py с копии сессии. Чужие сообщения — живой поток из
каналов/чатов аккаунта, бенчмарк ничего туда не пишет.

План — JSON:
  {"out": "/tmp/bench", "window_s": 900, "pings": 20,
   "targets": [{"name": "...", "cmd": [...], "cwd": "...",
                "before": ["sh ..."], "after": ["sh ..."],
                "driver": {"python": ..., "lib": ..., "session": ..., "api_id": ..., "api_hash": ...}}]}
after выполняется всегда (ошибка, Ctrl+C, SIGTERM).
"""

import json
import os
import shutil
import signal
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def mem(pid):
    """(RSS, PSS) в МБ."""
    vals = {}
    with open(f"/proc/{pid}/smaps_rollup") as f:
        for line in f:
            k, *v = line.split()
            if k in ("Rss:", "Pss:"):
                vals[k] = int(v[0]) // 1024
    return vals["Rss:"], vals["Pss:"]


def stats(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"rpc": 0, "foreign": 0, "methods": {}}


def ping(d, count, timeout):
    tmp = tempfile.mkdtemp(prefix="bench-drv-")
    try:
        with sqlite3.connect(d["session"]) as src, sqlite3.connect(os.path.join(tmp, "s.session")) as dst:
            src.backup(dst)
        r = subprocess.run(
            [d["python"], os.path.join(HERE, "bench_drive.py"), d["lib"], "s",
             str(d["api_id"]), d["api_hash"], str(count), str(timeout)],
            cwd=tmp, capture_output=True, text=True, timeout=timeout + 60,
        )
        if r.returncode:
            raise RuntimeError(r.stderr.strip()[-500:])
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sh(cmds):
    for c in cmds:
        log("$", c)
        subprocess.run(c, shell=True, check=True)


def measure(t, plan):
    out = os.path.join(plan["out"], t["name"] + ".stats")
    env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "benchhook"), ELYS_BENCH_OUT=out)
    res = {"name": t["name"]}
    samples, stop = [], threading.Event()
    with open(os.path.join(plan["out"], t["name"] + ".log"), "w") as logf:
        t0 = time.monotonic()
        p = subprocess.Popen(t["cmd"], cwd=t["cwd"], env=env, stdout=logf, stderr=subprocess.STDOUT)
        try:
            first = ping(t["driver"], 1, 180)
            if not first["ok"]:
                raise RuntimeError("бот не ответил на .ping за 180 с")
            res["start_s"] = round(time.monotonic() - t0 - first["lat_ms"][0] / 1000, 1)
            log(t["name"], "готов за", res["start_s"], "с")

            def sampler():
                while not stop.wait(5):
                    if p.poll() is None:
                        samples.append((time.monotonic() - t0, *mem(p.pid)))

            threading.Thread(target=sampler, daemon=True).start()
            res["rss_start_mb"], res["pss_start_mb"] = mem(p.pid)

            time.sleep(30)  # прогрев: догрузка кэшей, пропущенные апдейты
            a = stats(out)
            time.sleep(plan["window_s"])
            b = stats(out)
            foreign, rpc = b["foreign"] - a["foreign"], b["rpc"] - a["rpc"]
            res.update(window_s=plan["window_s"], foreign_msgs=foreign, rpc_window=rpc,
                       rpc_per_1000=round(rpc * 1000 / foreign) if foreign >= 100 else None)
            top = {k: v - a["methods"].get(k, 0) for k, v in b["methods"].items()}
            res["rpc_top"] = dict(sorted(top.items(), key=lambda kv: -kv[1])[:5])

            pg = ping(t["driver"], plan["pings"], plan["pings"] * 15)
            res["ping_median_ms"] = statistics.median(pg["lat_ms"]) if pg["lat_ms"] else None
            res["ping_ok"] = pg["ok"]
            res["rss_end_mb"], res["pss_end_mb"] = mem(p.pid)
        finally:
            stop.set()
            p.send_signal(signal.SIGINT)
            try:
                p.wait(30)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
    at5 = [s for s in samples if s[0] >= 300]
    if at5:
        res["rss_5min_mb"], res["pss_5min_mb"] = at5[0][1:]
    if samples:
        res["rss_max_mb"] = max(s[1] for s in samples)
    return res


def table(rows):
    cols = [("Старт, с", "start_s"), ("RSS после старта, МБ", "rss_start_mb"),
            ("RSS через 5 мин, МБ", "rss_5min_mb"), ("RSS в конце, МБ", "rss_end_mb"),
            ("PSS в конце, МБ", "pss_end_mb"), (".ping, медиана мс", "ping_median_ms"),
            ("Чужих сообщений за окно", "foreign_msgs"), ("RPC на 1000 чужих", "rpc_per_1000")]
    head = "| | " + " | ".join(r["name"] for r in rows) + " |"
    lines = [head, "|" + "---|" * (len(rows) + 1)]
    for title, key in cols:
        cells = ("—" if r.get(key) is None else str(r[key]) for r in rows)
        lines.append(f"| {title} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    with open(sys.argv[1]) as f:
        plan = json.load(f)
    os.makedirs(plan["out"], exist_ok=True)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    rows = []
    for t in plan["targets"]:
        log("▶", t["name"])
        try:
            sh(t.get("before", []))
            rows.append(measure(t, plan))
        except Exception as e:  # один упавший прогон не должен ронять остальные
            log("✗", t["name"], repr(e))
            rows.append({"name": t["name"], "error": repr(e)})
        finally:
            sh(t.get("after", []))
        with open(os.path.join(plan["out"], "results.json"), "w") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        log("✓", json.dumps(rows[-1], ensure_ascii=False))
    md = table(rows)
    with open(os.path.join(plan["out"], "table.md"), "w") as f:
        f.write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
