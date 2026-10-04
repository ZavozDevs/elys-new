from __future__ import annotations

import asyncio
import secrets
import string
import time
from dataclasses import dataclass, field

ALPHABET = string.ascii_letters + string.digits


@dataclass
class Unit:
    id: str
    kind: str
    owner_module: object
    allowed_ids: frozenset[int]
    expires: float
    data: dict = field(default_factory=dict)
    buttons: dict = field(default_factory=dict)
    next_button: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Units:
    def __init__(self, *, clock=time.monotonic):
        self.items: dict[str, Unit] = {}
        self.clock = clock

    def add(self, owner, kind, data, allowed_ids, *, ttl=86400):
        if not 0 < ttl <= 86400 * 30:
            raise ValueError("срок жизни формы должен быть от 0 до 30 дней")
        identity = "".join(secrets.choice(ALPHABET) for _ in range(8))
        while identity in self.items:
            identity = "".join(secrets.choice(ALPHABET) for _ in range(8))
        unit = Unit(identity, kind, owner, frozenset(allowed_ids), self.clock() + ttl, data)
        self.items[identity] = unit
        owner._resources.units.add(identity)
        return unit

    def get(self, identity):
        unit = self.items.get(identity)
        if unit and (unit.expires <= self.clock() or not unit.owner_module.loaded):
            self.remove(identity)
            return None
        return unit

    def remove(self, identity):
        unit = self.items.pop(identity, None)
        if unit:
            unit.owner_module._resources.units.discard(identity)

    def remove_owner(self, owner):
        for identity, unit in tuple(self.items.items()):
            if unit.owner_module is owner:
                self.remove(identity)

    def sweep(self):
        for identity in tuple(self.items):
            self.get(identity)

    async def clean(self):
        while True:
            await asyncio.sleep(60)
            self.sweep()

    def clear(self):
        for identity in tuple(self.items):
            self.remove(identity)
