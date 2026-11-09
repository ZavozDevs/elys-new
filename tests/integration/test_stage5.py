import asyncio
import sys
from pathlib import Path

import pytest

from tests.inline_helpers import install_inline
from tests.integration.test_loader import app as app

USER = sorted(p for p in (Path(__file__).parents[2] / "data" / "modules").glob("[!.]*.py"))


@pytest.mark.parametrize("source", USER, ids=lambda p: p.stem)
async def test_user_module_loads_and_unloads_clean(app, source):
    # перенесённые модули владельца (data/ не в git): загрузка, команды, выгрузка без утечек.
    install_inline(app)
    await app.kv.ns("core").flush()
    baseline, groups = set(asyncio.all_tasks()), dict(app.client.dispatcher.groups)
    module = await app.loader.install(source, trusted=True)
    resources = app.registry.entries[module.name]
    for command in resources.commands:
        assert app.router.get(command.name).owner is module
    await app.loader.unload(module.name)
    assert not resources.tasks and not resources.handlers
    assert app.client.dispatcher.groups == groups and not app.modules
    assert all(app.router.get(c.name) is None for c in resources.commands)
    assert f"elys.ext.{source.stem}" not in sys.modules
    assert not [t for t in asyncio.all_tasks() - baseline if "KV._flush_later" not in t.get_coro().__qualname__]
