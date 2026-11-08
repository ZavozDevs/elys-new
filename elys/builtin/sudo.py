# права доступа (§8): роли — .sudo, исключения — .rules. Только владелец: у команд нет ролей.

import re
from html import escape

from pyrogram import Client
from pyrogram.types import Message

from elys import Module, UserError, get_reply, respond

module = Module("Sudo")
t = module.t
ROLE = re.compile(r"[a-z][a-z0-9_]{0,31}")


def save(**changes) -> None:
    store = module.app.router.security.store
    store.update(changes)
    keep = {*store.get("roles", {}), *(str(rule[0]) for rule in store.get("rules", []))}
    store["names"] = {uid: name for uid, name in store.get("names", {}).items() if uid in keep}
    module.app.rebuild()


def name_of(uid) -> str:
    return escape(module.app.router.security.store.get("names", {}).get(str(uid), str(uid)))


async def subject(client: Client, message: Message, args: list[str]) -> tuple[int, list[str]]:
    # кто: here (этот чат), @username, id или автор сообщения, на которое ответили
    reply = await get_reply(message)
    if args and args[0] == "here":
        peer, args = message.chat, args[1:]
    elif reply is not None:
        peer = reply.from_user or reply.sender_chat or reply.chat
    elif args:
        try:
            peer = await client.get_chat(int(args[0]) if args[0].lstrip("-").isdigit() else args[0])
        except Exception:
            raise UserError(t("not_found", who=escape(args[0]))) from None
        args = args[1:]
    else:
        raise UserError(t("no_subject"))
    if peer.id == client.me.id:
        raise UserError(t("owner"))
    store = module.app.router.security.store
    title = getattr(peer, "title", None) or " ".join(filter(None, (peer.first_name, peer.last_name))) or str(peer.id)
    store["names"] = {**store.get("names", {}), str(peer.id): title}
    return peer.id, args


@module.command("sudo")
async def sudo(client: Client, message: Message) -> None:
    # [add|del <кто> [роль]] — роли: sudo — почти всё, support — справка и пинг
    args, roles = message.command[1:], dict(module.app.router.security.store.get("roles", {}))
    if not args:
        lines = (t("role_line", name=name_of(uid), id=uid, roles=", ".join(names)) for uid, names in roles.items())
        return await respond(message, t("roles", list="\n".join(lines) or t("empty")))
    if args[0] not in ("add", "del"):
        raise UserError(t("sudo_usage"))
    uid, rest = await subject(client, message, args[1:])
    role = rest[0].lower() if rest else "sudo" if args[0] == "add" else None
    if role is not None and (role == "owner" or not ROLE.fullmatch(role)):
        raise UserError(t("bad_role"))
    current = set(roles.get(str(uid), ()))
    current = current | {role} if args[0] == "add" else current - {role} if role else set()
    roles = {k: v for k, v in roles.items() if k != str(uid)} | ({str(uid): sorted(current)} if current else {})
    save(roles=roles)
    await respond(message, t("added" if args[0] == "add" else "removed", name=name_of(uid), role=role or "*"))


def target_of(name: str) -> str:
    command, owner = module.app.router.get(name.lower()), module.app.loader.resolve(name)
    if command is not None:
        return f"cmd:{command.name}"
    if owner is not None:
        return f"mod:{owner.name.lower()}"
    raise UserError(t("no_target", name=escape(name)))


def shown(target: str) -> str:
    kind, name = target.split(":", 1)
    return module.app.router.prefixes[0] + name if kind == "cmd" else t("module_target", name=escape(name))


@module.command("rules")
async def rules(client: Client, message: Message) -> None:
    # [allow|deny <кто|here> <команда|модуль>] [del <номер>] — исключения из ролей
    args, items = message.command[1:], list(module.app.router.security.store.get("rules", []))
    if not args:
        lines = (t("rule_line", n=n, sign=t("allow" if allow else "deny"), name=name_of(uid), target=shown(target))
                 for n, (uid, target, allow) in enumerate(items, 1))
        return await respond(message, t("rules", list="\n".join(lines) or t("empty")))
    if args[0] == "del" and len(args) == 2 and args[1].isdigit() and 0 < int(args[1]) <= len(items):
        uid, target, _ = items.pop(int(args[1]) - 1)
        save(rules=items)
        return await respond(message, t("rule_removed", name=name_of(uid), target=shown(target)))
    if args[0] not in ("allow", "deny"):
        raise UserError(t("rules_usage"))
    uid, rest = await subject(client, message, args[1:])
    if len(rest) != 1:
        raise UserError(t("rules_usage"))
    target, allow = target_of(rest[0]), args[0] == "allow"
    save(rules=[rule for rule in items if rule[:2] != [uid, target]] + [[uid, target, allow]])
    sign = t("allow" if allow else "deny")
    await respond(message, t("rule_added", sign=sign, name=name_of(uid), target=shown(target)))
