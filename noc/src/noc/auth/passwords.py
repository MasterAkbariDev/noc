import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{2,31}")

PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return PASSWORD_HASHER.check_needs_rehash(password_hash)


def check_password_rules(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("password must be 12-128 characters")


def normalize_username(name: str) -> str:
    normalized = name.strip().lower()
    if USERNAME_PATTERN.fullmatch(normalized) is None:
        raise ValueError(
            "username must be 3-32 characters: lower case letters, digits, dot, dash or underscore"
        )
    return normalized
