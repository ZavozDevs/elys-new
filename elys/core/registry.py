# владельцы ресурсов; удаление из диспетчера завершено до возврата, без фоновых гонок.

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from itertools import count


async def change_handler(client, handler, group: int, *, remove: bool = False):
    dispatcher = getattr(client, "dispatcher", None)
    if dispatcher is None:  # простой клиент без диспетчера, например в тестах sdk
        method = client.remove_handler if remove else client.add_handler
        method(handler, group)
        return
    # внутренний контракт wzgram 3.1.3 проверяется tests/compat.
    async with dispatcher._barrier():
        if remove:
            dispatcher.groups[group].remove(handler)
            if not dispatcher.groups[group]:
                del dispatcher.groups[group]
        else:
            dispatcher.groups.setdefault(group, []).append(handler)
            dispatcher.groups = OrderedDict(sorted(dispatcher.groups.items()))


@dataclass
class Resources:
    group: int
    commands: tuple = ()
    handlers: list = field(default_factory=list)
    tasks: set = field(default_factory=set)
    units: set[str] = field(default_factory=set)

    async def close(self):
        # команда может выключить собственный модуль; саму себя не ждём.
        current = asyncio.current_task()
        tasks = tuple(task for task in self.tasks if task is not current)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for client, handler in reversed(self.handlers):
            await change_handler(client, handler, self.group, remove=True)
        self.handlers.clear()
        self.tasks.clear()


class Registry:
    def __init__(self):
        self.entries: dict[str, Resources] = {}
        self._groups = count()

    def add(self, name: str, commands=()) -> Resources:
        if name in self.entries:
            raise ValueError(f"{name} уже загружен")
        resources = Resources(next(self._groups), tuple(commands))
        self.entries[name] = resources
        return resources

    def remove(self, name: str):
        self.entries.pop(name, None)
