import re
import uuid
from collections.abc import Iterable
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.models import FindingRow, ManagedResourceRow

PROCESS_NAME: Final = re.compile(r'"name":\s*"([^"]+)"')
CPU_MARKER: Final = "cpu_percent"
MATCHABLE_KINDS: Final = ("batch_unit", "systemd_unit")


def process_names(findings: Iterable[FindingRow]) -> list[str]:
    names: list[str] = []
    for finding in findings:
        for item in finding.evidence:
            excerpt = item.get("excerpt")
            if isinstance(excerpt, str) and CPU_MARKER in excerpt:
                names.extend(PROCESS_NAME.findall(excerpt))
    return list(dict.fromkeys(names))


def registered_process_match(
    names: Iterable[str], resources: Iterable[tuple[str, str]]
) -> str | None:
    """Return the resource id whose id tail or unit stem is one of the process names."""
    registered = list(resources)
    for name in names:
        for resource_id, unit in registered:
            stem = unit.removesuffix(".service")
            if name in (resource_id.split(":", 1)[-1], stem):
                return resource_id
    return None


async def resource_from_processes(
    session: AsyncSession, target_id: uuid.UUID, incident_id: uuid.UUID
) -> str | None:
    findings = await session.scalars(
        select(FindingRow).where(FindingRow.incident_id == incident_id)
    )
    names = process_names(findings)
    if not names:
        return None
    rows = await session.scalars(
        select(ManagedResourceRow).where(
            ManagedResourceRow.target_id == target_id,
            ManagedResourceRow.kind.in_(MATCHABLE_KINDS),
        )
    )
    return registered_process_match(names, [(row.resource_id, row.name) for row in rows])
