import base64
import hashlib
import ipaddress
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class KeyPurpose(StrEnum):
    BOOTSTRAP = "bootstrap"
    OPS = "ops"
    OPERATOR_SHELL = "operator-shell"


@dataclass(frozen=True)
class LifetimeRule:
    default_days: int
    min_days: int
    max_days: int
    needs_pin: bool
    allows_forced_command: bool
    has_paste_command: bool


LIFETIME_RULES: Final[dict[KeyPurpose, LifetimeRule]] = {
    KeyPurpose.BOOTSTRAP: LifetimeRule(1, 1, 7, False, False, True),
    KeyPurpose.OPS: LifetimeRule(90, 7, 365, True, True, True),
    KeyPurpose.OPERATOR_SHELL: LifetimeRule(30, 1, 90, True, False, False),
}

FORCED_COMMANDS: Final[dict[str, str]] = {
    "helper-status": "/usr/bin/systemctl is-active noc-sentinel.service",
}

LABEL_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
PUBLIC_KEY_PATTERN: Final = re.compile(r"^ssh-ed25519 [A-Za-z0-9+/]+={0,2}$")
MAX_PIN_ENTRIES: Final = 8
PIN_MAX_LENGTH: Final = 255
PASSPHRASE_BYTES: Final = 32
ROTATION_WARNING_DAYS: Final = 14
ROTATION_WARNING_SHARE: Final = 4
COMMENT_PREFIX: Final = "noc-key-"
EXPIRY_FORMAT: Final = "%Y%m%d%H%MZ"


class KeyRefused(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedKey:
    public_key: str
    private_key: str
    fingerprint: str
    passphrase: str | None


def private_key_secret_name(key_id: uuid.UUID) -> str:
    return f"ssh-key-{key_id}"


def passphrase_secret_name(key_id: uuid.UUID) -> str:
    return f"ssh-pass-{key_id}"


def key_comment(key_id: uuid.UUID) -> str:
    return f"{COMMENT_PREFIX}{key_id}"


def fingerprint_of(public_key: str) -> str:
    blob = base64.b64decode(public_key.split()[1])
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return f"SHA256:{digest}"


def generate_keypair(with_passphrase: bool) -> GeneratedKey:
    private = Ed25519PrivateKey.generate()
    passphrase = secrets.token_urlsafe(PASSPHRASE_BYTES) if with_passphrase else None
    encryption: serialization.KeySerializationEncryption = (
        serialization.BestAvailableEncryption(passphrase.encode())
        if passphrase
        else serialization.NoEncryption()
    )
    private_text = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, encryption
    ).decode()
    public_text = (
        private.public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode()
    )
    return GeneratedKey(public_text, private_text, fingerprint_of(public_text), passphrase)


def check_label(label: str) -> str:
    cleaned = label.strip()
    if LABEL_PATTERN.fullmatch(cleaned) is None:
        raise KeyRefused("the label must be 1-64 letters, digits, spaces, dots, dashes or _")
    return cleaned


def normalize_pin(pin: str | None) -> str | None:
    if pin is None or not pin.strip():
        return None
    entries = [entry.strip() for entry in pin.split(",") if entry.strip()]
    if len(entries) > MAX_PIN_ENTRIES:
        raise KeyRefused(f"pin at most {MAX_PIN_ENTRIES} addresses or networks")
    networks: list[str] = []
    for entry in entries:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError as error:
            raise KeyRefused(f"{entry!r} is not an IP address or network") from error
        networks.append(
            str(network.network_address) if network.num_addresses == 1 else str(network)
        )
    normalized = ",".join(networks)
    if len(normalized) > PIN_MAX_LENGTH:
        raise KeyRefused("the address pin is too long")
    return normalized


def check_rules(
    purpose: KeyPurpose, pin: str | None, forced_command: str | None, rotation_days: int
) -> None:
    rule = LIFETIME_RULES[purpose]
    if rule.needs_pin and pin is None:
        raise KeyRefused(f"a {purpose.value} key must be pinned to the NOC's address (from=)")
    if forced_command is not None:
        if not rule.allows_forced_command:
            raise KeyRefused(f"a {purpose.value} key cannot have a forced command")
        if forced_command not in FORCED_COMMANDS:
            raise KeyRefused(f"unknown forced command {forced_command}")
    if not rule.min_days <= rotation_days <= rule.max_days:
        raise KeyRefused(
            f"a {purpose.value} key lives {rule.min_days}-{rule.max_days} days, not {rotation_days}"
        )


def rotation_due_at(created_at: datetime, expires_at: datetime) -> datetime:
    lifetime = expires_at - created_at
    warning = min(timedelta(days=ROTATION_WARNING_DAYS), lifetime / ROTATION_WARNING_SHARE)
    return expires_at - warning


def authorized_keys_line(
    key_id: uuid.UUID,
    public_key: str,
    pin: str | None,
    forced_command: str | None,
    expires_at: datetime,
) -> str:
    if PUBLIC_KEY_PATTERN.fullmatch(public_key) is None:
        raise KeyRefused("the stored public key is not an ssh-ed25519 key")
    options = ["restrict", f'expiry-time="{expires_at.strftime(EXPIRY_FORMAT)}"']
    if pin is not None:
        options.append(f'from="{pin}"')
    if forced_command is not None:
        options.append(f'command="{FORCED_COMMANDS[forced_command]}"')
    return f"{','.join(options)} {public_key} {key_comment(key_id)}"
