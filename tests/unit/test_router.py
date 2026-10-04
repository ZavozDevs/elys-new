from types import SimpleNamespace

import pytest

from elys.core.router import Command, CommandConflict, Router, parse_args


class Owner:
    def __init__(self, name="Mod"):
        self.name = name
        self.spawned = []

    def spawn(self, coro):
        self.spawned.append(coro)


def msg(text=None, *, caption=None, outgoing=True):
    return SimpleNamespace(text=text, caption=caption, outgoing=outgoing, command=None)


def setup(prefixes=(".",)):
    owner, calls = Owner(), []

    async def callback(client, message):
        calls.append(message.command)

    router = Router(prefixes)
    router.add(Command("ping", callback, owner, aliases=("p",)))
    return router, owner, calls


async def run(router, owner, message):
    await router.dispatch(None, message)
    for coro in owner.spawned:
        await coro
    owner.spawned.clear()


@pytest.mark.parametrize(
    ("text", "command"),
    [
        (".ping", ["ping"]),
        (".PING a 'b c' \"d\"", ["ping", "a", "b c", "d"]),
        (".p\nx", ["ping", "x"]),
    ],
)
async def test_dispatch(text, command):
    router, owner, calls = setup()
    await run(router, owner, msg(text))
    assert calls == [command]


@pytest.mark.parametrize("text", [None, "", "ping", ". ping", ".", ".unknown", "!ping"])
async def test_ignored(text):
    router, owner, calls = setup()
    await run(router, owner, msg(text))
    assert calls == []


async def test_caption_and_incoming():
    router, owner, calls = setup()
    await run(router, owner, msg(caption=".ping"))
    await run(router, owner, msg(".ping", outgoing=False))  # по умолчанию — только владелец
    assert calls == [["ping"]]


async def test_longest_prefix_wins():
    router, owner, calls = setup(prefixes=(".", ".."))
    await run(router, owner, msg("..ping"))
    assert calls == [["ping"]]


async def test_custom_allow():
    router, owner, calls = setup()
    router.allow = lambda message, command: True
    await run(router, owner, msg(".ping", outgoing=False))
    assert calls == [["ping"]]


def test_conflict_is_all_or_nothing():
    router, _, _ = setup()
    other = Owner("Other")
    with pytest.raises(CommandConflict, match="Mod"):
        router.add(Command("new", None, other), Command("p", None, other))
    assert router.get("new") is None
    assert router.get("p").owner is not other


def test_remove_owner():
    router, owner, _ = setup()
    router.remove(owner)
    assert router.get("ping") is None
    assert router.get("p") is None


@pytest.mark.parametrize("prefixes", [(), ("",), (" ",)])
def test_bad_prefixes(prefixes):
    with pytest.raises(ValueError):
        Router(prefixes)


def test_parse_args():
    assert parse_args(r"""a "b \"c\"" '' d""") == ["a", 'b "c"', "", "d"]


@pytest.mark.parametrize("same_owner", [True, False])
def test_conflict_inside_batch_is_atomic(same_owner):
    router, owner, _ = setup()
    other = owner if same_owner else Owner("Other")
    with pytest.raises(CommandConflict):
        router.add(Command("new", None, owner, aliases=("x",)), Command("x", None, other))
    assert router.get("new") is None
    assert router.get("x") is None
    assert router.get("ping").owner is owner


def test_same_owner_cannot_silently_replace_command():
    router, owner, _ = setup()
    original = router.get("ping")
    with pytest.raises(CommandConflict):
        router.add(Command("ping", None, owner))
    assert router.get("ping") is original


async def test_prefix_order_is_user_order_but_matching_is_longest_first():
    router, owner, calls = setup(("!", ".", "!", ".."))
    assert router.prefixes == ("!", ".", "..")
    await run(router, owner, msg("..ping"))
    await run(router, owner, msg("!ping"))
    assert calls == [["ping"], ["ping"]]
