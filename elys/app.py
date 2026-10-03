"""App: сборка сервисов и жизненный цикл."""

from __future__ import annotations

import itertools
import logging
from contextlib import AsyncExitStack
from importlib import import_module

from pyrogram import idle

from elys import __version__, builtin
from elys.core import clients
from elys.core.clients import ElysClient, Login
from elys.core.router import GROUP as ROUTER_GROUP
from elys.core.router import Router
from elys.sdk.module import Module, find
from elys.settings import Settings
from elys.storage.kv import KV

log = logging.getLogger(__name__)


class App:
    client: ElysClient
    router: Router
    kv: KV

    def __init__(self, settings: Settings, *, login: Login | None = None) -> None:
        self.settings = settings
        self.login = login
        self.modules: dict[str, Module] = {}
        self._groups = itertools.count()  # у каждого модуля своя группа диспетчера

    async def run(self) -> None:
        settings = self.settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        # остановка — в обратном порядке: модули → клиент → kv
        async with AsyncExitStack() as stack:
            self.kv = await KV.open(settings.data_dir / "elys.db")
            stack.push_async_callback(self.kv.close)

            self.router = Router(self.kv.ns("core").get("prefixes", settings.prefixes))
            self.client = clients.user(settings, version=__version__, login=self.login)
            log.info("подключаюсь к Telegram…")
            await self.client.start()
            stack.push_async_callback(self.client.stop)
            for handler in self.router.handlers():
                self.client.add_handler(handler, ROUTER_GROUP)

            stack.push_async_callback(self.unload_all)
            for name in builtin.NAMES:
                await self.load(find(vars(import_module(f"elys.builtin.{name}")), name))

            # как пользоваться, при первом запуске объясняет builtin welcome
            log.info("Elys %s работает в аккаунте %s. Остановить — Ctrl+C", __version__, self.client.me.full_name)
            await idle()

    async def load(self, module: Module) -> None:
        if module.name in self.modules:
            raise ValueError(f"модуль {module.name} уже загружен")
        await module.attach(self, group=next(self._groups))
        self.modules[module.name] = module
        self._rebuild_gate()

    async def unload_all(self) -> None:
        for module in reversed(self.modules.values()):
            await module.detach()
        self.modules.clear()
        self._rebuild_gate()

    def _rebuild_gate(self) -> None:
        self.client.gate.rebuild(scope for module in self.modules.values() for scope in module.scopes)
