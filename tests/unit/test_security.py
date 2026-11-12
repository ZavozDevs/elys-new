from types import SimpleNamespace

from elys.core.ratelimit import RateLimit
from elys.core.router import Command
from elys.core.security import Security

MOD = SimpleNamespace(name="Mod")
PING = Command("ping", None, MOD, roles=frozenset({"sudo", "support"}))
EVAL = Command("e", None, MOD, roles=frozenset({"sudo"}))
SUDO = Command("sudo", None, MOD)


def security(**store):
    s = Security(store)
    s.compile([PING, EVAL, SUDO])
    return s


def test_roles():
    s = security(roles={"5": ["sudo"], "6": ["support"], "7": ["friends"]})
    assert s.allowed(5, 5, PING) and s.allowed(5, 5, EVAL) and not s.allowed(5, 5, SUDO)
    assert s.allowed(6, 1, PING) and not s.allowed(6, 1, EVAL)
    assert not s.allowed(7, 1, PING) and not s.allowed(8, 1, PING)
    assert s.trusted_ids == {5, 6, 7}


def test_rules_deny_beats_allow_and_command_beats_module():
    s = security(
        roles={"5": ["sudo"]},
        rules=[
            [5, "cmd:e", False],
            [6, "mod:mod", True],
            [6, "cmd:sudo", False],
            [-1, "cmd:ping", True],
            [-2, "mod:mod", False],
        ],
    )
    assert not s.allowed(5, 5, EVAL) and s.allowed(5, 5, PING)
    assert s.allowed(6, 6, PING) and not s.allowed(6, 6, SUDO)
    assert s.allowed(9, -1, PING) and not s.allowed(9, -1, EVAL)
    assert not s.allowed(5, -2, PING)
    assert s.trusted_ids == {5, 6, -1}


def test_ratelimit_refills():
    now = [0.0]
    limit = RateLimit(2, 10.0, clock=lambda: now[0])
    assert [limit.take(1, "x") for _ in range(3)] == [True, True, False]
    assert limit.take(2, "x") and limit.take(1, "y")
    now[0] = 5.0
    assert limit.take(1, "x") and not limit.take(1, "x")
