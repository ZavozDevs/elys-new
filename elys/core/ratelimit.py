# лимит выполнения команд не-владельцем: token bucket на (отправитель, команда), без await.

from __future__ import annotations

from collections.abc import Callable
from time import monotonic


class RateLimit:
    def __init__(self, rate: int = 5, per: float = 10.0, clock: Callable[[], float] = monotonic) -> None:
        self.rate, self.per, self.clock = rate, per, clock
        self.buckets: dict[tuple[int, str], tuple[float, float]] = {}

    def take(self, sender: int, command: str) -> bool:
        now = self.clock()
        tokens, last = self.buckets.get((sender, command), (self.rate, now))
        tokens = min(self.rate, tokens + (now - last) * self.rate / self.per)
        self.buckets[sender, command] = (tokens - (tokens >= 1), now)
        return tokens >= 1
