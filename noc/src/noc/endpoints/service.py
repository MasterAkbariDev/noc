import asyncio
import re
import time
from typing import Any, Final
from urllib.parse import urlsplit

import httpx

CONNECT_TIMEOUT_SECONDS: Final = 5.0
WEB_TIMEOUT_SECONDS: Final = 10.0
BANNER_MAX_LENGTH: Final = 80
SSH_BANNER: Final = re.compile(r"^SSH-\d\.\d-\S+")
HOST_PATTERN: Final = re.compile(r"^[A-Za-z0-9.\-]{1,255}$")


def clean_host(raw: str) -> str:
    host = raw.strip()
    if not HOST_PATTERN.fullmatch(host):
        raise ValueError("the address must be a host name or an IP address")
    return host


def clean_url(raw: str | None) -> str | None:
    if raw is None or raw.strip() == "":
        return None
    url = raw.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("the web address must start with http:// or https://")
    return url


async def check_ssh(host: str, port: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), CONNECT_TIMEOUT_SECONDS
        )
    except (OSError, TimeoutError) as error:
        return {"open": False, "error": type(error).__name__, "ms": None}
    try:
        line = (await asyncio.wait_for(reader.readline(), CONNECT_TIMEOUT_SECONDS)).decode(
            "ascii", "replace"
        )
    except (OSError, TimeoutError):
        line = ""
    finally:
        writer.close()
    banner = line.strip()[:BANNER_MAX_LENGTH]
    return {
        "open": True,
        "banner": banner if SSH_BANNER.match(banner) else None,
        "ms": int((time.monotonic() - started) * 1000),
    }


async def check_web(url: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=WEB_TIMEOUT_SECONDS) as http:
            response = await http.get(url)
    except httpx.HTTPError as error:
        return {"ok": False, "error": type(error).__name__, "ms": None}
    return {
        "ok": response.status_code < 500,
        "status": response.status_code,
        "ms": int((time.monotonic() - started) * 1000),
    }


async def run_check(host: str, ssh_port: int, url: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {"ssh": await check_ssh(host, ssh_port)}
    if url:
        result["web"] = await check_web(url)
    result["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return result
