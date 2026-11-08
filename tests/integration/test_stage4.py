import asyncio
import sqlite3
import subprocess
import zipfile
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from elys.builtin import backup, updater
from elys.storage.files import restore_pending
from tests.inline_helpers import click, install_inline, last_unit
from tests.integration.test_loader import app as app
from tests.integration.test_stage2_commands import Msg as Base


class Msg(Base):
    def __init__(self, text, *, sender=None, chat=99, reply=None):
        super().__init__(text, outgoing=sender is None)
        self.id, self.chat = 1, SimpleNamespace(id=chat, title="Группа", full_name="Группа")
        self.from_user = sender and SimpleNamespace(id=sender, first_name="Маша", last_name=None)
        self.reply_to_message = reply

    async def reply(self, text=None, **kwargs):
        self.edits.append(text)
        return self


async def invoke(app, text, **kwargs):
    message = Msg(text, **kwargs)
    await app.router.dispatch(app.client, message)
    if message.command:
        owner = app.router.get(message.command[0]).owner
        loops = {loop.task for loop in owner._loops}  # периодические задачи не завершаются
        await asyncio.gather(*(task for task in tuple(owner._resources.tasks) if task not in loops))
    return message


async def load(app, *names):
    install_inline(app)
    for name in names:
        await app.load(import_module(f"elys.builtin.{name}").module)


async def test_sudo_and_rules_in_dm_and_group(app):
    await load(app, "sudo", "ping", "terminal")

    async def get_chat(peer):
        return SimpleNamespace(id=int(peer), first_name="Маша", last_name=None)

    app.client.get_chat = get_chat
    assert (await invoke(app, ".ping", sender=5, chat=5)).edits == []
    assert "Выдано" in (await invoke(app, ".sudo add 5")).edits[0]
    assert 5 in app.client.gate.trusted
    assert (await invoke(app, ".ping", sender=5, chat=5)).edits  # личка
    assert (await invoke(app, ".sudo add 6", sender=5, chat=5)).edits == []  # .sudo/.rules — только владелец
    assert (await invoke(app, ".rules allow 6 sudo", sender=5, chat=5)).edits == []
    await invoke(app, ".sudo add 6 owner")
    assert "6" not in app.router.security.store["roles"]

    await invoke(app, ".rules deny 5 ping")
    assert (await invoke(app, ".ping", sender=5, chat=5)).edits == []
    assert (await invoke(app, ".t echo ok", sender=5, chat=5)).edits  # остальное у sudo осталось
    await invoke(app, ".rules allow here ping", chat=-100)
    assert -100 in app.client.gate.trusted
    assert (await invoke(app, ".ping", sender=7, chat=-100)).edits  # группа: правило на чат
    assert (await invoke(app, ".ping", sender=5, chat=-100)).edits == []  # запрет сильнее
    assert (await invoke(app, ".t id", sender=7, chat=-100)).edits == []

    rules = (await invoke(app, ".rules")).edits[0]
    assert "1. ⛔ Маша → .ping" in rules and "2. ✅ Группа → .ping" in rules
    await invoke(app, ".rules del 1")
    await invoke(app, ".sudo del 5")
    assert app.router.security.store["roles"] == {} and set(app.router.security.store["names"]) == {"-100"}
    assert app.client.gate.trusted == {-100}


async def test_terminal_and_info(app):
    await load(app, "terminal", "info")
    screen = (await invoke(app, ".t echo hi; exit 3")).edits[-1]
    assert "hi" in screen and "<code>3</code>" in screen
    app.client.get_messages = None
    assert "CPU" in (await invoke(app, ".info")).edits[-1]
    assert (await invoke(app, ".info", sender=9, chat=9)).edits == []


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


async def test_update_pulls_and_restarts(app, tmp_path, monkeypatch):
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "t")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "t@t")
    remote, work, other = tmp_path / "remote.git", tmp_path / "work", tmp_path / "other"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(tmp_path, "clone", "-q", str(remote), str(other))
    git(other, "commit", "-q", "--allow-empty", "-m", "one")
    git(other, "push", "-q", "origin", "HEAD")
    git(tmp_path, "clone", "-q", str(remote), str(work))
    monkeypatch.setattr(updater, "REPO", work)
    reboots = []
    monkeypatch.setattr(app, "reboot", lambda: reboots.append(1), raising=False)
    await load(app, "updater")

    assert "Обновлений нет" in (await invoke(app, ".update")).edits[-1]
    git(other, "commit", "-q", "--allow-empty", "-m", "two")
    git(other, "push", "-q", "origin", "HEAD")
    old = git(work, "rev-parse", "--short", "HEAD")
    await invoke(app, ".update")
    unit = last_unit(app)
    assert "two" in unit.data["text"]
    await click(app, unit, "Обновить")
    assert git(work, "rev-parse", "HEAD") == git(other, "rev-parse", "HEAD") and reboots == [1]
    assert app.kv.ns("updater")["notice"][2] == old


def db(path):
    with sqlite3.connect(path) as connection:
        connection.execute("create table if not exists kv (ns text, key text, value text, primary key (ns, key))")
        connection.execute("insert or replace into kv values ('a', 'b', '1')")


async def test_backup_restore_and_zip_slip(app, tmp_path, monkeypatch):
    data, target = tmp_path / "data", tmp_path / "target"
    (data / "modules").mkdir(parents=True)
    (target / "modules").mkdir(parents=True)
    db(data / "elys.db")
    (data / "modules" / "mod.py").write_text("x = 1")
    (data / "session.session").write_text("secret")
    backup.pack(data, tmp_path / "copy.zip")
    assert sorted(zipfile.ZipFile(tmp_path / "copy.zip").namelist()) == ["elys.db", "modules/mod.py"]

    (tmp_path / "copy.zip").rename(target / "restore.zip")
    (target / "elys.db-wal").write_text("old")
    restore_pending(target)
    assert (target / "modules" / "mod.py").read_text() == "x = 1" and not (target / "restore.zip").exists()
    assert not (target / "elys.db-wal").exists() and not (target / "session.session").exists()

    with zipfile.ZipFile(target / "restore.zip", "w") as archive:
        for name in ("elys.db", "../evil.py", "/abs.py", "modules/../x.py", "modules/sub/a.py", "settings.toml"):
            archive.writestr(name, "bad")
    restore_pending(target)
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == [
        "elys.db", "modules/mod.py"]
    assert not any(tmp_path.glob("*.py")) and not (tmp_path / "x.py").exists()


async def test_restore_command_validates_and_reboots(app, tmp_path, monkeypatch):
    reboots = []
    monkeypatch.setattr(app, "reboot", lambda: reboots.append(1), raising=False)
    await load(app, "backup")
    db(tmp_path / "good.db")
    with zipfile.ZipFile(tmp_path / "good.zip", "w") as archive:
        archive.write(tmp_path / "good.db", "elys.db")

    def file(content):
        async def download(path):
            Path(path).write_bytes(content)  # noqa: ASYNC240
        return SimpleNamespace(document=object(), download=download)

    assert "Ответь" in (await invoke(app, ".restore")).edits[-1]
    assert "не копия" in (await invoke(app, ".restore", reply=file(b"junk"))).edits[-1]
    assert not (tmp_path / "restore.zip").exists() and reboots == []
    good = file((tmp_path / "good.zip").read_bytes())
    assert "Восстанавливаю" in (await invoke(app, ".restore", reply=good)).edits[-1]
    assert (tmp_path / "restore.zip").exists() and reboots == [1]


async def test_remote_uses_etag(app, monkeypatch):
    from urllib.error import HTTPError
    sent = []

    async def fake_run(*command):
        return {"get-url": "git@github.com:ZavozDevs/Elys-new.git", "--abbrev-ref": "origin/master"}.get(command[2], "")

    class Response:
        headers = {"ETag": "W/1"}  # noqa: RUF012
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def read(self):
            return b"abc123\n"

    def fake_urlopen(request, timeout):
        sent.append((request.full_url, request.get_header("If-none-match")))
        if len(sent) > 1:
            raise HTTPError(request.full_url, 304, "", {}, None)
        return Response()

    monkeypatch.setattr(updater, "run", fake_run)
    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    await load(app, "updater")
    await updater.watch.stop()  # своя фоновая проверка не нужна в тесте
    sent.clear()
    app.kv.ns("updater").clear()
    assert await updater.remote() == "abc123"
    assert await updater.remote() == "abc123"
    assert sent[0][0].endswith("/repos/ZavozDevs/Elys-new/commits/master")
    assert [etag for _, etag in sent] == [None, "W/1"]


async def test_auto_backup_only_on_change_and_rotates(app, tmp_path, monkeypatch):
    (tmp_path / "modules").mkdir(exist_ok=True)
    db(tmp_path / "elys.db")
    sent, deleted = [], []

    async def send_document(chat_id, archive, **kwargs):
        sent.append((chat_id, kwargs["message_thread_id"], zipfile.ZipFile(archive).namelist()))
        return SimpleNamespace(id=len(sent))

    async def delete_messages(chat_id, message_id):
        deleted.append(message_id)

    await load(app, "backup")
    await backup.auto.stop()
    app.forum = SimpleNamespace(available=True, chat_id=-100, state={"topics": {"backups": 7}})
    app.bot = SimpleNamespace(send_document=send_document, delete_messages=delete_messages)
    backup.module.config["keep"] = 2
    state = app.kv.ns("backup")

    async def tick(changed):
        if changed:
            with sqlite3.connect(tmp_path / "elys.db") as connection:
                connection.execute("insert into kv values ('a', ?, '1')", (str(len(sent)) + "x",))
        state["last"] = 0
        await backup.auto.callback(app.client)

    await tick(False)
    await tick(False)  # те же данные — не шлём
    assert sent == [(-100, 7, ["elys.db"])]
    await tick(True)
    await tick(True)
    assert len(sent) == 3 and deleted == [1] and state["messages"] == [[-100, 2], [-100, 3]]
    await backup.auto.callback(app.client)  # интервал не вышел
    app.forum.available = False
    await tick(True)  # без форума — никуда не шлём
    assert len(sent) == 3
