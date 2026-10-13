import pytest

from noc.auth.passwords import (
    DUMMY_HASH,
    check_password_rules,
    hash_password,
    needs_rehash,
    normalize_username,
    verify_password,
)
from noc.auth.roles import Role, role_allows

PASSWORD = "correct horse battery"


def test_hash_then_verify_round_trip() -> None:
    password_hash = hash_password(PASSWORD)
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, PASSWORD) is True


def test_wrong_password_does_not_verify() -> None:
    assert verify_password(hash_password(PASSWORD), "wrong horse battery") is False


def test_garbage_hash_does_not_verify() -> None:
    assert verify_password("not-a-hash", PASSWORD) is False


def test_dummy_hash_never_verifies_a_guess() -> None:
    assert verify_password(DUMMY_HASH, PASSWORD) is False


def test_fresh_hash_does_not_need_rehash() -> None:
    assert needs_rehash(hash_password(PASSWORD)) is False


@pytest.mark.parametrize("length", [11, 129])
def test_password_outside_length_rules_is_rejected(length: int) -> None:
    with pytest.raises(ValueError, match="12-128 characters"):
        check_password_rules("x" * length)


@pytest.mark.parametrize("length", [12, 128])
def test_password_at_length_limits_is_accepted(length: int) -> None:
    check_password_rules("x" * length)


def test_username_is_trimmed_and_lower_cased() -> None:
    assert normalize_username("  Alice.Ops ") == "alice.ops"


@pytest.mark.parametrize("name", ["ab", "a" * 33, "-alice", "al ice", "alice@ops", ""])
def test_invalid_username_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="username"):
        normalize_username(name)


@pytest.mark.parametrize(
    ("have", "need", "allowed"),
    [
        (Role.VIEWER, Role.VIEWER, True),
        (Role.VIEWER, Role.OPERATOR, False),
        (Role.VIEWER, Role.ADMIN, False),
        (Role.OPERATOR, Role.VIEWER, True),
        (Role.OPERATOR, Role.OPERATOR, True),
        (Role.OPERATOR, Role.ADMIN, False),
        (Role.ADMIN, Role.VIEWER, True),
        (Role.ADMIN, Role.OPERATOR, True),
        (Role.ADMIN, Role.ADMIN, True),
    ],
)
def test_role_ladder(have: Role, need: Role, allowed: bool) -> None:
    assert role_allows(have, need) is allowed
