import base64
import shlex
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from noc.fleet.commands import (
    NOC_IP_PLACEHOLDER,
    HostSpec,
    add_key_command,
    check_address,
    check_ssh_user,
    noc_ip_from_pin,
    paste_steps,
    remove_key_command,
)
from noc.fleet.keys import (
    KeyPurpose,
    KeyRefused,
    authorized_keys_line,
    check_label,
    check_rules,
    fingerprint_of,
    generate_keypair,
    normalize_pin,
    rotation_due_at,
)

KEY_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
EXPIRES = datetime(2026, 11, 16, 9, 30, tzinfo=UTC)
HOST = HostSpec("demo-2", "203.0.113.7", "ops", "lab")


def public_key() -> str:
    return generate_keypair(with_passphrase=False).public_key


def test_generated_key_is_ed25519_with_matching_fingerprint() -> None:
    generated = generate_keypair(with_passphrase=False)

    assert generated.public_key.startswith("ssh-ed25519 ")
    assert generated.private_key.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert generated.fingerprint == fingerprint_of(generated.public_key)
    assert generated.passphrase is None


def test_passphrase_protects_the_private_key() -> None:
    generated = generate_keypair(with_passphrase=True)
    assert generated.passphrase is not None

    with pytest.raises(TypeError):
        serialization.load_ssh_private_key(generated.private_key.encode(), password=None)
    loaded = serialization.load_ssh_private_key(
        generated.private_key.encode(), password=generated.passphrase.encode()
    )
    assert isinstance(loaded, Ed25519PrivateKey)


def test_fingerprint_matches_openssh_format() -> None:
    blob = base64.b64decode(public_key().split()[1])

    fingerprint = fingerprint_of(f"ssh-ed25519 {base64.b64encode(blob).decode()}")

    assert fingerprint.startswith("SHA256:")
    assert not fingerprint.endswith("=")


@pytest.mark.parametrize(
    ("pin", "expected"),
    [
        (None, None),
        ("  ", None),
        ("198.51.100.4", "198.51.100.4"),
        ("198.51.100.4/32, 10.0.0.0/8", "198.51.100.4,10.0.0.0/8"),
        ("2001:db8::1", "2001:db8::1"),
    ],
)
def test_pin_is_normalized(pin: str | None, expected: str | None) -> None:
    assert normalize_pin(pin) == expected


@pytest.mark.parametrize("pin", ["example.com", '1.2.3.4" command="sh', "1.2.3.4,*"])
def test_pin_refuses_anything_but_addresses(pin: str) -> None:
    with pytest.raises(KeyRefused):
        normalize_pin(pin)


def test_label_refuses_quotes() -> None:
    with pytest.raises(KeyRefused):
        check_label("it's mine")


def test_ops_key_needs_a_pin() -> None:
    with pytest.raises(KeyRefused, match="pinned"):
        check_rules(KeyPurpose.OPS, None, None, 90)


def test_bootstrap_key_is_short_lived() -> None:
    check_rules(KeyPurpose.BOOTSTRAP, None, None, 1)
    with pytest.raises(KeyRefused, match="1-7 days"):
        check_rules(KeyPurpose.BOOTSTRAP, None, None, 30)


def test_forced_command_comes_from_the_catalogue_only() -> None:
    check_rules(KeyPurpose.OPS, "198.51.100.4", "helper-status", 90)
    with pytest.raises(KeyRefused, match="unknown forced command"):
        check_rules(KeyPurpose.OPS, "198.51.100.4", "bash", 90)
    with pytest.raises(KeyRefused):
        check_rules(KeyPurpose.BOOTSTRAP, None, "helper-status", 1)


def test_authorized_keys_line_is_restricted_and_expires() -> None:
    key = public_key()

    line = authorized_keys_line(KEY_ID, key, "198.51.100.4", "helper-status", EXPIRES)

    assert line.startswith('restrict,expiry-time="202611160930Z",from="198.51.100.4",command="')
    assert line.endswith(f"{key} noc-key-{KEY_ID}")
    assert "'" not in line


def test_authorized_keys_line_refuses_a_foreign_key() -> None:
    with pytest.raises(KeyRefused):
        authorized_keys_line(KEY_ID, "ssh-rsa AAAA", None, None, EXPIRES)


def test_rotation_warning_is_two_weeks_or_a_quarter() -> None:
    created = EXPIRES - timedelta(days=90)
    assert rotation_due_at(created, EXPIRES) == EXPIRES - timedelta(days=14)
    short = EXPIRES - timedelta(days=1)
    assert rotation_due_at(short, EXPIRES) == EXPIRES - timedelta(hours=6)


@pytest.mark.parametrize("user", ["root", "Ops", "ops;rm", "a b", ""])
def test_ssh_user_refuses_root_and_odd_names(user: str) -> None:
    with pytest.raises(KeyRefused):
        check_ssh_user(user)


def test_address_must_be_an_ip() -> None:
    assert check_address(" 203.0.113.7 ") == "203.0.113.7"
    with pytest.raises(KeyRefused):
        check_address("demo.example.com")


def test_add_key_command_is_idempotent_and_parses_as_shell() -> None:
    line = authorized_keys_line(KEY_ID, public_key(), "198.51.100.4", None, EXPIRES)

    command = add_key_command("ops", KEY_ID, line)

    assert "useradd --create-home --shell /bin/bash ops" in command
    assert f"grep -qF noc-key-{KEY_ID}" in command
    assert "sudo -l -U ops" in command
    tokens = shlex.split(command)
    assert line in tokens


def test_remove_key_command_targets_only_this_key() -> None:
    assert remove_key_command("ops", KEY_ID) == (
        f"sed -i '/ noc-key-{KEY_ID}$/d' /home/ops/.ssh/authorized_keys"
    )


def test_paste_steps_fill_the_noc_ip_from_a_single_pin() -> None:
    line = authorized_keys_line(KEY_ID, public_key(), "198.51.100.4", None, EXPIRES)

    steps = paste_steps(HOST, KEY_ID, line, "198.51.100.4")

    assert [step.where for step in steps] == [
        "on demo-2, as root",
        "on demo-2, from a copy of the repository",
        "on the NOC host",
    ]
    assert "--noc-ip 198.51.100.4" in steps[1].command
    assert "--environment lab" in steps[1].command
    assert steps[2].command.startswith("noc targets add demo-2 203.0.113.7")


def test_noc_ip_is_a_placeholder_for_networks() -> None:
    assert noc_ip_from_pin("10.0.0.0/8") == NOC_IP_PLACEHOLDER
    assert noc_ip_from_pin(None) == NOC_IP_PLACEHOLDER
