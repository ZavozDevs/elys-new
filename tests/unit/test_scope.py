from elys.core.scope import CHANNEL, GROUP, PRIVATE, Matcher, Scope, key


def test_flags_or_within_category_and_across():
    scope = (Scope.PRIVATE | Scope.GROUP | Scope.INCOMING).default_kind(edited=False)
    assert scope.keys() == {key(PRIVATE), key(GROUP)}


def test_all_is_every_chat_and_direction_of_one_kind():
    keys = Scope.ALL.default_kind(edited=False).keys()
    assert len(keys) == 6
    assert key(CHANNEL, out=True) in keys
    assert key(PRIVATE, edited=True) not in keys


def test_default_kind_keeps_explicit():
    scope = (Scope.EDITED | Scope.PRIVATE).default_kind(edited=False)
    assert scope.keys() == {key(PRIVATE, edited=True), key(PRIVATE, out=True, edited=True)}


def test_chats_union_and_restriction():
    scope = Scope.chats({1}) | Scope.chats({2}) | Scope.GROUP
    assert scope.chat_ids == {1, 2}
    assert scope.chat_types == 1 << GROUP
    assert (Scope.PRIVATE | Scope.chats({3})).chat_ids == {3}


def test_equality():
    assert Scope.PRIVATE | Scope.INCOMING == Scope.INCOMING | Scope.PRIVATE
    assert hash(Scope.chats([1, 2])) == hash(Scope.chats([2, 1]))


def test_matcher():
    matcher = Matcher(
        [
            (Scope.PRIVATE | Scope.INCOMING).default_kind(edited=False),
            (Scope.chats({-5}) | Scope.GROUP).default_kind(edited=True),
        ]
    )
    assert matcher(key(PRIVATE), 42)
    assert not matcher(key(GROUP), 42)
    assert matcher(key(GROUP, edited=True), -5)
    assert not matcher(key(GROUP), -5)
    assert not Matcher()
