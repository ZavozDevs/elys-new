# периодическая задача принадлежит модулю, повторный start не создаёт копию.

import asyncio
import math


class Loop:
    def __init__(self, module, callback, interval, autostart):
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("интервал должен быть положительным конечным числом")
        self.module, self.callback = module, callback
        self.interval, self.autostart = interval, autostart
        self.task = None

    def start(self):
        if self.task is None or self.task.done():
            self.task = self.module.spawn(self._run())
        return self.task

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def _run(self):
        while self.module.loaded:
            try:
                await self.callback(self.module.client)
            except Exception:
                self.module.log.exception("периодическая задача упала")
            await asyncio.sleep(self.interval)
