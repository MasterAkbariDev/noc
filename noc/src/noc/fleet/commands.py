import ipaddress
import re
import shlex
import uuid
from dataclasses import dataclass
from typing import Final

from noc.fleet.keys import KeyRefused, key_comment

SSH_USER_PATTERN: Final = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
HOST_NAME_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
FORBIDDEN_USERS: Final = frozenset({"root"})
SENTINEL_PORT: Final = 9444
NOC_IP_PLACEHOLDER: Final = "NOC_IP_HERE"
PKI_DIR: Final = "./noc-pki"
HMAC_KEY_FILE: Final = "./noc-worker.key"
WHEEL_DIR: Final = "./noc-wheels"
SUDO_OK_TEXT: Final = "sudo scope OK: the user has no sudo rights"
SUDO_WARNING_TEXT: Final = "WARNING: the user has sudo rights; remove them before you go on"


@dataclass(frozen=True)
class HostSpec:
    name: str
    address: str
    ssh_user: str
    environment: str


@dataclass(frozen=True)
class CommandStep:
    title: str
    where: str
    command: str


def check_ssh_user(user: str) -> str:
    if SSH_USER_PATTERN.fullmatch(user) is None or user in FORBIDDEN_USERS:
        raise KeyRefused("the SSH user must be a plain lower-case Linux user name, never root")
    return user


def check_host_name(name: str) -> str:
    if HOST_NAME_PATTERN.fullmatch(name) is None:
        raise KeyRefused("the name must be 1-63 letters, digits, dots, dashes or _")
    return name


def check_address(address: str) -> str:
    try:
        return str(ipaddress.ip_address(address.strip()))
    except ValueError as error:
        raise KeyRefused(f"{address!r} is not an IP address") from error


def home_of(user: str) -> str:
    return f"/home/{user}"


def authorized_keys_path(user: str) -> str:
    return f"{home_of(user)}/.ssh/authorized_keys"


def noc_ip_from_pin(pin: str | None) -> str:
    if pin is None or "," in pin or "/" in pin:
        return NOC_IP_PLACEHOLDER
    return pin


def add_key_command(user: str, key_id: uuid.UUID, line: str) -> str:
    keys = authorized_keys_path(user)
    comment = key_comment(key_id)
    parts = [
        f"id -u {user} >/dev/null 2>&1 || useradd --create-home --shell /bin/bash {user}",
        f"passwd --lock {user} >/dev/null",
        f"install -d -m 700 -o {user} -g {user} {home_of(user)}/.ssh",
        f"touch {keys}",
        f"grep -qF {shlex.quote(comment)} {keys} || printf '%s\\n' {shlex.quote(line)} >> {keys}",
        f"chown {user}:{user} {keys}",
        f"chmod 600 {keys}",
        sudo_check(user),
    ]
    return "; ".join(parts)


def sudo_check(user: str) -> str:
    return (
        f"if sudo -l -U {user} 2>/dev/null | grep -q 'may run'; "
        f"then echo {shlex.quote(SUDO_WARNING_TEXT)}; else echo {shlex.quote(SUDO_OK_TEXT)}; fi"
    )


def remove_key_command(user: str, key_id: uuid.UUID) -> str:
    comment = key_comment(key_id)
    return f"sed -i {shlex.quote(f'/ {comment}$/d')} {authorized_keys_path(user)}"


def install_helper_command(host: HostSpec, noc_ip: str) -> str:
    return (
        f"sudo bash deploy/target/install.sh --noc-ip {noc_ip} --pki-dir {PKI_DIR} "
        f"--target-name {host.name} --with-sentinel --key-file {HMAC_KEY_FILE} "
        f"--wheel-dir {WHEEL_DIR} --environment {host.environment} --dry-run"
    )


def register_command(host: HostSpec) -> str:
    return (
        f"noc targets add {host.name} {host.address} https://{host.address}:{SENTINEL_PORT} "
        f"--key-id noc-worker --env {host.environment}"
    )


def paste_steps(host: HostSpec, key_id: uuid.UUID, line: str, pin: str | None) -> list[CommandStep]:
    return [
        CommandStep(
            "Create the ops user and allow the key",
            f"on {host.name}, as root",
            add_key_command(host.ssh_user, key_id, line),
        ),
        CommandStep(
            "Install the NOC helper (drop --dry-run once the plan looks right)",
            f"on {host.name}, from a copy of the repository",
            install_helper_command(host, noc_ip_from_pin(pin)),
        ),
        CommandStep("Register the server", "on the NOC host", register_command(host)),
    ]


def rotation_steps(
    host: HostSpec, old_key_id: uuid.UUID, new_key_id: uuid.UUID, new_line: str
) -> list[CommandStep]:
    combined = (
        f"{add_key_command(host.ssh_user, new_key_id, new_line)}; "
        f"{remove_key_command(host.ssh_user, old_key_id)}"
    )
    return [CommandStep("Swap the key", f"on {host.name}, as root", combined)]


def revoke_steps(host: HostSpec, key_id: uuid.UUID) -> list[CommandStep]:
    return [
        CommandStep(
            "Remove the key line",
            f"on {host.name}, as root",
            remove_key_command(host.ssh_user, key_id),
        )
    ]


def offboard_steps(host: HostSpec, key_ids: list[uuid.UUID], pin_ip: str) -> list[CommandStep]:
    removals = [remove_key_command(host.ssh_user, key_id) for key_id in key_ids]
    steps = [
        CommandStep(
            "Stop and remove the NOC helper",
            f"on {host.name}, from a copy of the repository",
            f"sudo bash deploy/target/install.sh --uninstall --noc-ip {pin_ip}",
        )
    ]
    if removals:
        steps.append(
            CommandStep("Remove the NOC's keys", f"on {host.name}, as root", "; ".join(removals))
        )
    return steps
