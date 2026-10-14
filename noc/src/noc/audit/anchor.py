import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import GENESIS_HASH, verify_chain
from noc.db.models import AuditEntry

ANCHOR_VERSION: Final = 1
MINIMUM_KEY_BYTES: Final = 16
ANCHOR_FILE_PREFIX: Final = "anchor-"
ANCHOR_FILE_SUFFIX: Final = ".json"


class AnchorError(Exception):
    pass


class AnchorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    created_at: datetime
    last_entry_id: int = Field(ge=0)
    head_hash: str = Field(min_length=64, max_length=64)


class Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: AnchorBody
    mac: str = Field(min_length=64, max_length=64)


@dataclass(frozen=True)
class AnchorCheck:
    name: str
    problem: str | None


def read_key(path: Path) -> bytes:
    try:
        key = path.read_bytes().strip()
    except OSError as error:
        raise AnchorError(f"cannot read the anchor key {path}: {error.strerror}") from error
    if len(key) < MINIMUM_KEY_BYTES:
        raise AnchorError(f"the anchor key {path} is shorter than {MINIMUM_KEY_BYTES} bytes")
    return key


def canonical(body: AnchorBody) -> bytes:
    return json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()


def sign_body(key: bytes, body: AnchorBody) -> str:
    return hmac.new(key, canonical(body), hashlib.sha256).hexdigest()


def anchor_filename(body: AnchorBody) -> str:
    stamp = body.created_at.strftime("%Y%m%dT%H%M%SZ")
    return f"{ANCHOR_FILE_PREFIX}{stamp}-{body.last_entry_id}{ANCHOR_FILE_SUFFIX}"


async def create_anchor(session: AsyncSession, key: bytes, now: datetime) -> Anchor:
    broken = await verify_chain(session)
    if broken is not None:
        raise AnchorError(f"the audit chain is broken at entry {broken}; not anchoring it")
    last = await session.scalar(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1))
    body = AnchorBody(
        version=ANCHOR_VERSION,
        created_at=now,
        last_entry_id=0 if last is None else last.id,
        head_hash=GENESIS_HASH if last is None else last.hash,
    )
    return Anchor(body=body, mac=sign_body(key, body))


def parse_anchor(raw: str) -> Anchor:
    try:
        return Anchor.model_validate_json(raw)
    except ValueError as error:
        raise AnchorError("not a valid anchor file") from error


async def check_anchor(session: AsyncSession, key: bytes, anchor: Anchor) -> str | None:
    if anchor.body.version != ANCHOR_VERSION:
        return f"unknown anchor version {anchor.body.version}"
    if not hmac.compare_digest(sign_body(key, anchor.body), anchor.mac):
        return "the signature does not match: the file or the key is not the original"
    if anchor.body.last_entry_id == 0:
        return None
    entry = await session.get(AuditEntry, anchor.body.last_entry_id)
    if entry is None:
        return f"entry {anchor.body.last_entry_id} is missing: the log was truncated"
    if entry.hash != anchor.body.head_hash:
        return f"entry {anchor.body.last_entry_id} has a different hash: the log was rewritten"
    return None


def load_anchors(directory: Path) -> list[tuple[str, Anchor | AnchorError]]:
    loaded: list[tuple[str, Anchor | AnchorError]] = []
    for path in sorted(directory.glob(f"{ANCHOR_FILE_PREFIX}*{ANCHOR_FILE_SUFFIX}")):
        try:
            loaded.append((path.name, parse_anchor(path.read_text(encoding="utf-8"))))
        except OSError as error:
            loaded.append((path.name, AnchorError(f"cannot read the file: {error.strerror}")))
        except AnchorError as error:
            loaded.append((path.name, error))
    return loaded


async def check_anchors(
    session: AsyncSession, key: bytes, loaded: list[tuple[str, Anchor | AnchorError]]
) -> list[AnchorCheck]:
    checks: list[AnchorCheck] = []
    for name, item in loaded:
        if isinstance(item, AnchorError):
            checks.append(AnchorCheck(name, str(item)))
        else:
            checks.append(AnchorCheck(name, await check_anchor(session, key, item)))
    return checks
