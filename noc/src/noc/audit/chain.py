import hashlib
import json
from datetime import UTC
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.models import AuditEntry

GENESIS_HASH = "0" * 64
AUDIT_LOCK_KEY = 7_401_001


def entry_hash(prev_hash: str, record: dict[str, Any]) -> str:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def hashed_fields(entry: AuditEntry) -> dict[str, Any]:
    return {
        # Hash the time in UTC so the chain does not depend on the database's timezone.
        "ts": entry.ts.astimezone(UTC).isoformat(),
        "actor": entry.actor,
        "action": entry.action,
        "subject": entry.subject,
        "payload": entry.payload,
    }


async def append_audit(
    session: AsyncSession, actor: str, action: str, subject: str, payload: dict[str, Any]
) -> AuditEntry:
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": AUDIT_LOCK_KEY})
    last_hash = await session.scalar(
        select(AuditEntry.hash).order_by(AuditEntry.id.desc()).limit(1)
    )
    entry = AuditEntry(ts=utc_now(), actor=actor, action=action, subject=subject, payload=payload)
    entry.prev_hash = last_hash or GENESIS_HASH
    entry.hash = entry_hash(entry.prev_hash, hashed_fields(entry))
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession) -> int | None:
    expected_prev = GENESIS_HASH
    entries = await session.scalars(select(AuditEntry).order_by(AuditEntry.id))
    for entry in entries:
        if entry.prev_hash != expected_prev:
            return entry.id
        if entry.hash != entry_hash(entry.prev_hash, hashed_fields(entry)):
            return entry.id
        expected_prev = entry.hash
    return None
