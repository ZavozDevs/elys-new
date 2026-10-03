"""клиент юзербота: дефолты без лишних запросов + гейт коротких апдейтов."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from pyrogram import Client, raw
from pyrogram.enums import ParseMode
from pyrogram.types import User

from elys.settings import Settings

from .gate import Gate, GateDispatcher

Login = Callable[[Client], Awaitable[User]]

_SHORT = (raw.types.UpdateShortMessage, raw.types.UpdateShortChatMessage)


class NotLoggedIn(RuntimeError):
    pass


class ElysClient(Client):
    def __init__(self, *args: Any, login: Login | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.login = login
        self.gate = Gate(self.listeners)
        self.dispatcher = GateDispatcher(self, self.gate)

    async def authorize(self) -> User:
        # вместо англоязычных подсказок wzgram — свой вход; без терминала спрашивать некого
        if self.login is None:
            raise NotLoggedIn
        return await self.login(self)

    async def handle_updates(self, updates: Any) -> Any:
        # wzgram на каждое короткое сообщение делает GetDifference — чужие режем до него
        if isinstance(updates, _SHORT) and not self.gate.short(updates):
            self.last_update_time = datetime.now()
            self._last_update_monotonic = time.monotonic()
            await self._save_update_state((0, updates.pts, None, updates.date, None))
            return None
        return await super().handle_updates(updates)


def user(settings: Settings, *, version: str, login: Login | None = None) -> ElysClient:
    return ElysClient(
        "elys",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        workdir=settings.data_dir,
        login=login,
        fetch_replies=False,  # иначе get_messages на каждый реплай в любом чате
        fetch_topics=False,
        fetch_stories=False,
        fetch_stickers=False,
        skip_updates=True,  # старые команды после рестарта не выполняем
        auto_no_updates=True,
        parse_mode=ParseMode.HTML,
        rate_limits=settings.rate_limits,
        max_concurrent_transmissions=4,
        device_model="Elys",
        app_version=version,
    )
