# права (§8): роли и правила → trusted_ids, role_of, overrides. горячий путь — два dict.get.

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .router import Command

ROLES = ("owner", "sudo", "support")  # owner — только у владельца; остальные имена — свои группы


class Security:
    # store: {"roles": {id: [роль]}, "rules": [[кто, "cmd:имя"|"mod:имя", allow]], "names": {id: имя}}

    def __init__(self, store: MutableMapping[str, Any] | None = None) -> None:
        self.store = {} if store is None else store
        self.bits = {role: bit for bit, role in enumerate(ROLES)}
        self.compile()

    def mask(self, roles: Iterable[str]) -> int:
        return sum(1 << self.bits.setdefault(role, len(self.bits)) for role in set(roles))

    def compile(self, commands: Iterable[Command] = ()) -> None:
        roles, rules, commands = self.store.get("roles", {}), self.store.get("rules", []), tuple(commands)
        self.role_of = {int(uid): self.mask(names) for uid, names in roles.items()}
        overrides = {(uid, c.name): True for uid, m in self.role_of.items() for c in commands if m & self.mask(c.roles)}
        # правило на модуль, потом на команду: точное сильнее общего
        for subject, target, allow in sorted(rules, key=lambda rule: rule[1].startswith("cmd:")):
            overrides.update({(subject, c.name): allow for c in commands
                              if target in (f"cmd:{c.name}", f"mod:{c.owner.name.lower()}")})
        self.overrides = overrides
        self.trusted_ids = frozenset(self.role_of) | {subject for subject, _, allow in rules if allow}

    def allowed(self, sender: int, chat: int, command: Command) -> bool:
        # запрет человеку или чату сильнее любого разрешения; разрешает роль или allow.
        user, place = self.overrides.get((sender, command.name)), self.overrides.get((chat, command.name))
        return user is not False and place is not False and bool(user or place)
