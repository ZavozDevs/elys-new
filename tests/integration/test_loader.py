import asyncio
import sys
from types import SimpleNamespace

import pytest
from pyrogram.types import User

from elys import Module
from elys.app import App
from elys.core.clients import ElysClient
from elys.core.loader import Loader, LoadError, metadata
from elys.core.router import Router
from elys.sdk.module import find
from elys.settings import Settings
from elys.storage.kv import KV

SOURCE = '''import asyncio
from elys import Module, Scope, Config
module = Module("Hello", version="1", config=Config(count=Config.value(1)))
@module.command("hello")
async def hello(client, message):
    await asyncio.sleep(60)
@module.on_message(scope=Scope.ALL)
async def watch(client, message):
    await asyncio.sleep(60)
@module.loop(60, autostart=True)
async def tick(client):
    await asyncio.sleep(60)
@module.on_load
async def load(client):
    module.spawn(asyncio.sleep(60))
@module.on_ready
async def ready(client):
    module.db["ready"] = True
'''


@pytest.fixture
async def app(tmp_path):
    app = App(Settings(api_id=1, api_hash="test", data_dir=tmp_path))
    app.kv = await KV.open(tmp_path / "db", delay=60)
    app.router = Router(["."])
    app.client = ElysClient("test", api_id=1, api_hash="test", in_memory=True)
    app.client.me = User(id=1, first_name="test")
    app.loader = Loader(app, find)
    yield app
    await app.unload_all()
    await app.kv.close()
    app.client.executor.shutdown(wait=True)


@pytest.fixture
def source(tmp_path):
    source = tmp_path / "hello.py"
    source.write_text(SOURCE)
    return source


async def test_real_dispatcher_and_tasks_return_to_baseline(app, source):
    # считаем реальные группы wzgram и все задачи цикла, не вызовы моков.
    await app.kv.ns("core").flush()
    baseline = set(asyncio.all_tasks())
    groups = dict(app.client.dispatcher.groups)
    for _ in range(3):
        module = await app.loader.install(source, trusted=True)
        assert module.db["ready"] is True
        assert module.config["count"] == 1
        module.config["count"] = 2
        resources = app.registry.entries["Hello"]
        assert len(app.client.dispatcher.groups) == len(groups) + 1
        assert len(resources.handlers) == 1
        assert resources.commands[0].name == "hello"
        module.spawn(app.router.get("hello").callback(app.client, None))
        handler = resources.handlers[0][1]
        watcher = asyncio.create_task(handler.callback(app.client, None))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await app.loader.unload("hello")
        await watcher
        assert not resources.tasks and not resources.handlers
        assert not app.registry.entries and not app.modules
        assert app.client.dispatcher.groups == groups
        assert app.router.get("hello") is None
        assert not app.client.gate.matcher
        assert "elys.ext.hello" not in sys.modules
        # kv — отдельная задача write-behind, закрываем её в конце проверки.
        assert not [t for t in asyncio.all_tasks() - baseline
                    if "KV._flush_later" not in t.get_coro().__qualname__]
        app.kv.ns("cfg:Hello")["count"] = 1


async def test_update_rollback_and_failed_update_restore_working_code(app, source):
    await app.loader.install(source, trusted=True)
    source.write_text(SOURCE.replace('version="1"', 'version="2"'))
    await app.loader.install(source, trusted=True)
    assert app.modules["Hello"].version == "2"
    await app.loader.reload("Hello")  # перечитывание без изменений не должно съесть предыдущую версию
    await app.loader.reload("Hello", rollback=True)
    assert app.modules["Hello"].version == "1"
    previous = (app.loader.directory / ".prev" / "hello.py").read_text()
    source.write_text(SOURCE + '\n@module.on_load\nasync def broken(client):\n    raise ValueError("broken")\n')
    with pytest.raises(ValueError, match="broken"):
        await app.loader.install(source, trusted=True)
    assert app.modules["Hello"].version == "1"
    assert (app.loader.directory / "hello.py").read_text() == SOURCE
    assert (app.loader.directory / ".prev" / "hello.py").read_text() == previous
    assert len(app.client.dispatcher.groups) == len(app.registry.entries) == 1


async def test_package_relative_imports_reload_and_cleanup(app, tmp_path):
    package = tmp_path / "weather"
    package.mkdir()
    (package / "__init__.py").write_text('from .part import VERSION\nfrom elys import Module\n'
                                       'module = Module("Weather", version=VERSION)\n')
    (package / "part.py").write_text('VERSION = "1"\n')
    await app.loader.install(package, trusted=True)
    assert "elys.ext.weather.part" in sys.modules
    (package / "part.py").write_text('VERSION = "2"\n')
    await app.loader.install(package, trusted=True)
    assert app.modules["Weather"].version == "2"
    await app.loader.reload("Weather", rollback=True)
    assert app.modules["Weather"].version == "1"
    await app.loader.unload("Weather")
    assert not any(name.startswith("elys.ext.weather") for name in sys.modules)


async def test_disabled_survives_autoload_and_purge_is_explicit(app, source):
    await app.loader.install(source, trusted=True)
    app.kv.ns("mod:Hello")["value"] = 7
    app.kv.ns("cfg:Hello")["count"] = 3
    await app.loader.unload("Hello")
    await app.loader.load_all()
    assert not app.modules
    await app.loader.load("hello")
    assert app.modules["Hello"].config["count"] == 3
    assert app.modules["Hello"].db["value"] == 7
    await app.loader.unload("Hello", purge=True)
    assert not app.kv.ns("mod:Hello") and not app.kv.ns("cfg:Hello")


async def test_conflict_and_failed_ready_leave_no_resources(app, source, tmp_path):
    await app.loader.install(source, trusted=True)
    other = tmp_path / "other.py"
    other.write_text(SOURCE.replace('Module("Hello"', 'Module("Other"'))
    with pytest.raises(Exception, match="hello"):
        await app.loader.install(other, trusted=True)
    assert set(app.modules) == {"Hello"}
    assert len(app.registry.entries) == len(app.client.dispatcher.groups) == 1
    assert "elys.ext.other" not in sys.modules
    other.write_text('from elys import Module\nmodule = Module("Other")\n'
                     '@module.on_ready\nasync def ready(client):\n    raise ValueError("ready")\n')
    with pytest.raises(ValueError, match="ready"):
        await app.loader.install(other, trusted=True)
    assert set(app.modules) == {"Hello"}
    assert "elys.ext.other" not in sys.modules


async def test_trust_builtin_protection_and_path_validation(app, source):
    with pytest.raises(LoadError, match="доступ"):
        await app.loader.install(source)
    builtin = Module("Builtin")
    await app.load(builtin)
    with pytest.raises(LoadError, match="встроенный"):
        await app.loader.unload("Builtin")
    for name in ("../hello", "/tmp/hello", "hello.py"):
        with pytest.raises(LoadError):
            await app.loader.load(name)


async def test_cancelled_load_restores_previous_module(app, source):
    await app.loader.install(source, trusted=True)
    source.write_text(SOURCE + '\n@module.on_load\nasync def cancel(client):\n    raise asyncio.CancelledError\n')
    with pytest.raises(asyncio.CancelledError):
        await app.loader.install(source, trusted=True)
    assert app.modules["Hello"].loaded
    assert len(app.registry.entries) == len(app.client.dispatcher.groups) == 1


async def test_url_install_with_real_http(app):
    requests = []

    async def serve(reader, writer):
        requests.append(await reader.readuntil(b"\r\n\r\n"))
        data = SOURCE.encode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        module = await app.loader.install(f"http://127.0.0.1:{port}/hello.py", trusted=True)
    assert module.name == "Hello" and len(requests) == 1


def test_ast_metadata_never_executes_code(tmp_path):
    path = tmp_path / "x.py"
    path.write_text('raise RuntimeError("must not run")\nfrom elys import Module as M\n'
                    'module = M("X", requires=["packaging>=24"], banner="https://example.org/a.png")')
    assert metadata(path) == {"requires": ["packaging>=24"], "banner": "https://example.org/a.png"}
    path.write_text('from elys import Module\nm = Module("X", requires=__import__("os").getcwd())')
    with pytest.raises(LoadError, match="без вычислений"):
        metadata(path)


async def test_duplicate_load_does_not_replace_imports(app, source):
    await app.loader.install(source, trusted=True)
    original = sys.modules["elys.ext.hello"]
    with pytest.raises(LoadError, match="уже загружен"):
        await app.loader.load("hello")
    assert sys.modules["elys.ext.hello"] is original
    assert app.modules["Hello"] is original.module


async def test_reload_uses_last_working_source_for_recovery(app, source):
    await app.loader.install(source, trusted=True)
    installed = app.loader.directory / "hello.py"
    installed.write_text(SOURCE.replace('version="1"', 'version="2"'))
    await app.loader.reload("Hello")
    assert app.modules["Hello"].version == "2"
    await app.loader.reload("Hello", rollback=True)
    assert app.modules["Hello"].version == "1"
    installed.write_text(SOURCE + '\n@module.on_ready\nasync def fail(client):\n    raise ValueError("ready")\n')
    with pytest.raises(ValueError, match="ready"):
        await app.loader.reload("Hello")
    assert app.modules["Hello"].version == "1"
    assert installed.read_text() == SOURCE


async def test_force_restores_conflicting_module_on_failure(app, source, tmp_path):
    await app.loader.install(source, trusted=True)
    other = tmp_path / "other.py"
    other.write_text(SOURCE.replace('Module("Hello"', 'Module("Other"') +
                     '\n@module.on_load\nasync def fail(client):\n    raise ValueError("load")\n')
    with pytest.raises(ValueError, match="load"):
        await app.loader.install(other, trusted=True, force=True)
    assert set(app.modules) == {"Hello"}
    assert app.router.get("hello").owner.name == "Hello"
    other.write_text(SOURCE.replace('Module("Hello"', 'Module("Other"'))
    await app.loader.install(other, trusted=True, force=True)
    assert set(app.modules) == {"Other"}
    assert app.kv.ns("core")["disabled_modules"] == ["hello"]
    assert app.router.get("hello").owner.name == "Other"
    assert len(app.registry.entries) == len(app.client.dispatcher.groups) == 1


async def test_module_can_unload_itself_without_cancelling_dispatcher(app, source):
    source.write_text('from elys import Module\nmodule = Module("Self")\n'
                      '@module.command("bye")\nasync def bye(client, message):\n'
                      '    await module.app.loader.unload("Self")\n')
    item = await app.loader.install(source, trusted=True)
    message = SimpleNamespace(text=".bye", caption=None, chat=None)
    task = item.spawn(app.router.get("bye").callback(app.client, message))
    await asyncio.wait_for(task, 1)
    assert task.exception() is None
    assert not app.modules and not app.registry.entries
    assert app.router.get("bye") is None
