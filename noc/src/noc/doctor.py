import asyncio
import ssl
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
import yaml
from sqlalchemy import text

from noc.config import Settings
from noc.db.models import Target
from noc.db.session import SessionFactory
from noc.policy.loader import load_policy
from noc.tools.sentinel_client import SentinelDirectory, build_sentinel_http, build_ssl_context
from noc.tools.spec import TargetRef

Status = Literal["ok", "warn", "fail"]

CERT_WARN_DAYS = 14
CERT_FAIL_DAYS = 2
SECONDS_PER_DAY = 86400
PROMETHEUS_READY_TIMEOUT_SECONDS = 3.0
TLS_PROBE_TIMEOUT_SECONDS = 5.0
HTTPS_DEFAULT_PORT = 443


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str


def ok(name: str, detail: str) -> CheckResult:
    return CheckResult(name, "ok", detail)


def warn(name: str, detail: str) -> CheckResult:
    return CheckResult(name, "warn", detail)


def fail(name: str, detail: str) -> CheckResult:
    return CheckResult(name, "fail", detail)


async def check_database(sessions: SessionFactory, expected_head: str) -> CheckResult:
    name = "database"
    try:
        async with sessions() as session:
            current = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception as error:
        return fail(name, f"cannot read the database: {type(error).__name__}")
    if current != expected_head:
        return fail(name, f"schema is at {current}, the code expects {expected_head}")
    return ok(name, f"reachable, schema at {current}")


def check_policy(policy_file: Path) -> CheckResult:
    name = "policy"
    try:
        document = load_policy(policy_file)
    except Exception as error:
        return fail(name, f"{policy_file} does not load: {type(error).__name__}: {error}")
    return ok(name, f"{policy_file.name} loads, {len(document.actions)} actions")


async def check_prometheus(prometheus_url: str) -> CheckResult:
    name = "prometheus"
    url = f"{prometheus_url.rstrip('/')}/-/ready"
    try:
        async with httpx.AsyncClient(timeout=PROMETHEUS_READY_TIMEOUT_SECONDS) as http:
            response = await http.get(url)
    except httpx.HTTPError as error:
        return fail(name, f"{url} is not reachable: {type(error).__name__}")
    if response.status_code != 200:
        return fail(name, f"{url} answered HTTP {response.status_code}")
    return ok(name, "ready")


def check_llm(settings: Settings, environment: dict[str, str]) -> CheckResult:
    name = "llm"
    if settings.llm_mode != "live":
        return ok(name, f"mode is {settings.llm_mode}, no provider keys needed")
    providers = yaml.safe_load(settings.llm_providers_file.read_text())["providers"]
    missing = [
        provider
        for provider, definition in providers.items()
        if not environment.get(definition["api_key_env"])
        and not environment.get(definition["api_keys_env"])
    ]
    if len(missing) == len(providers):
        return fail(name, "live mode but no provider has an API key")
    if missing:
        return warn(name, f"no API key for {', '.join(sorted(missing))}; its fallback is off")
    return ok(name, f"live mode, keys present for {', '.join(sorted(providers))}")


def check_key_file(key_dir: Path, key_id: str) -> CheckResult:
    name = f"key {key_id}"
    path = key_dir / f"{key_id}.key"
    try:
        mode = path.stat().st_mode
    except OSError:
        return fail(name, f"{path} is missing or unreadable")
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return warn(name, f"{path} is readable by group or others; use mode 0600")
    return ok(name, f"{path.name} present, owner only")


async def peer_certificate_expiry(url: str, context: ssl.SSLContext) -> float:
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or HTTPS_DEFAULT_PORT
    _, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=context, server_hostname=host),
        TLS_PROBE_TIMEOUT_SECONDS,
    )
    try:
        ssl_object = writer.get_extra_info("ssl_object")
        certificate = ssl_object.getpeercert()
        return float(ssl.cert_time_to_seconds(str(certificate["notAfter"])))
    finally:
        writer.close()


async def check_certificate(name: str, url: str, context: ssl.SSLContext | None) -> CheckResult:
    label = f"certificate {name}"
    if not url.startswith("https://") or context is None:
        return warn(label, f"{url} is not checked over TLS with the NOC's CA")
    try:
        expires_at = await peer_certificate_expiry(url, context)
    except (OSError, ssl.SSLError, TimeoutError, KeyError) as error:
        return fail(label, f"cannot read the certificate of {url}: {type(error).__name__}")
    days = (expires_at - time.time()) / SECONDS_PER_DAY
    if days < CERT_FAIL_DAYS:
        return fail(label, f"expires in {days:.1f} days")
    if days < CERT_WARN_DAYS:
        return warn(label, f"expires in {days:.0f} days")
    return ok(label, f"valid for {days:.0f} more days")


async def check_sentinel(reference: TargetRef, settings: Settings) -> CheckResult:
    name = f"sentinel {reference.name}"
    http = build_sentinel_http(
        settings.sentinel_ca_file,
        settings.sentinel_client_cert,
        settings.sentinel_client_key,
        settings.sentinel_timeout_seconds,
    )
    try:
        async with http:
            inventory = (
                await SentinelDirectory(settings.sentinel_key_dir, http)
                .client_for(reference)
                .inventory()
            )
    except Exception as error:
        return fail(name, f"inventory call failed: {type(error).__name__}: {error}")
    state = "halted" if inventory.halted else "running"
    return ok(name, f"answers a signed request, {len(inventory.resources)} resources, {state}")


def reference_for(target: Target) -> TargetRef:
    return TargetRef(
        id=target.id,
        name=target.name,
        sentinel_url=target.sentinel_url,
        hmac_key_id=target.hmac_key_id,
        environment=target.environment,
        data_policy=target.llm_data_policy,
    )


async def check_targets(settings: Settings, targets: list[Target]) -> list[CheckResult]:
    context = build_ssl_context(
        settings.sentinel_ca_file, settings.sentinel_client_cert, settings.sentinel_client_key
    )
    results: list[CheckResult] = []
    for target in targets:
        results.append(check_key_file(settings.sentinel_key_dir, target.hmac_key_id))
        results.append(await check_certificate(target.name, target.sentinel_url, context))
        results.append(await check_sentinel(reference_for(target), settings))
    return results
