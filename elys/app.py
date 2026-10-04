# app: сборка сервисов и жизненный цикл.

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from importlib import import_module

from pyrogram import idle

from elys import __version__, builtin
from elys.core import clients
from elys.core.clients import ElysClient, Login
from elys.core.loader import Loader
from elys.core.registry import Registry
from elys.core.router import GROUP as ROUTER_GROUP
from elys.core.router import Router
from elys.inline.bot import BotService
from elys.inline.form import Inline
from elys.inline.forum import Forum
from elys.log import telegram_handler
from elys.sdk.module import Module, find
from elys.settings import Settings
from elys.storage.files import private_directory
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
        self.registry = Registry()
        self.premium = False
        self.banners_enabled = True
        self.language = "ru"
        self.bot = None
        self.bot_service = None
        self.forum = None
        self.inline = None
        self.loader = None

    async def run(self) -> None:
        settings = self.settings
        private_directory(settings.data_dir)
        # остановка — в обратном порядке: модули → клиент → kv
        async with AsyncExitStack() as stack:
            self.kv = await KV.open(settings.data_dir / "elys.db")
            stack.push_async_callback(self.kv.close)

            self.router = Router(self.kv.ns("core").get("prefixes", settings.prefixes))
            core = self.kv.ns("core")
            self.router.set_aliases(core.get("aliases", {}))
            self.language = core.get("language", "ru")
            self.banners_enabled = core.get("banners", True)
            self.loader = Loader(self, find)
            self.client = clients.user(settings, version=__version__, login=self.login)
            # без сессии сначала мастер входа — не мешаем ему.
            if (settings.data_dir / f"{clients.SESSION}.session").exists():
                log.info("подключаюсь к Telegram…")
            await self.client.start()
            stack.push_async_callback(self.client.stop)
            self.premium = bool(self.client.me.is_premium)
            for handler in self.router.handlers():
                self.client.add_handler(handler, ROUTER_GROUP)

            # Сначала ищем форум (в нём может сидеть бот), затем бота; создаём только то, чего нет.
            self.forum = Forum(self)
            self.bot_service = BotService(self)
            await self.bot_service.start()
            stack.push_async_callback(self.bot_service.stop)
            await self.forum.ensure()
            self.inline = Inline(self)
            stack.push_async_callback(self.inline.close)
            await self.inline.start()
            telegram = telegram_handler()
            telegram.attach(lambda text: self.forum.send("errors", text))
            stack.push_async_callback(telegram.stop)

            stack.push_async_callback(self.unload_all)
            for name in builtin.NAMES:
                await self.load(find(vars(import_module(f"elys.builtin.{name}")), name))

            for module in tuple(self.modules.values()):
                await module.ready()
            await self.loader.load_all()

            # как пользоваться, при первом запуске объясняет builtin welcome
            log.info("модули: %s", ", ".join(self.modules))
            log.info(
                "Elys %s запущен · %s · остановить — Ctrl+C",
                __version__,
                self.client.me.full_name,
                extra={"mark": "ok"},
            )
            await idle()

    async def load(self, module: Module) -> None:
        if module.name in self.modules:
            raise ValueError(f"модуль {module.name} уже загружен")
        resources = self.registry.add(module.name, module.commands)
        try:
            await module.attach(self, group=resources.group, resources=resources)
        except BaseException:
            self.registry.remove(module.name)
            raise
        self.modules[module.name] = module
        self._rebuild_gate()

    async def unload(self, name: str) -> None:
        module = self.modules.pop(name)
        try:
            await module.detach()
        finally:
            self.registry.remove(name)
            self._rebuild_gate()

    async def unload_all(self) -> None:
        try:
            async with AsyncExitStack() as stack:
                for name in tuple(self.modules):
                    stack.push_async_callback(self.unload, name)
        finally:
            self.modules.clear()
            if self.loader is not None:
                await self.loader.close()
            self._rebuild_gate()

    def _rebuild_gate(self) -> None:
        self.client.gate.rebuild(scope for module in self.modules.values() for scope in module.scopes)
