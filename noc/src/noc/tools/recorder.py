import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import update

from noc.db.models import Incident, ToolCall
from noc.db.session import SessionFactory, transaction
from noc.tools.spec import ToolContext


@dataclass(frozen=True)
class ToolCallRecord:
    ref: str
    context: ToolContext
    tool: str
    args: dict[str, Any]
    permission: str
    decision: str
    decision_reason: str
    ok: bool
    started_at: datetime
    duration_ms: int
    result: dict[str, Any] | None
    result_text: str
    truncated: bool
    injection_flags: list[str]

    def result_sha256(self) -> str:
        canonical = json.dumps(self.result, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()


class ToolCallRecorder(Protocol):
    async def next_ref(self, context: ToolContext) -> str: ...

    async def record(self, record: ToolCallRecord) -> None: ...


class MemoryToolCallRecorder:
    def __init__(self) -> None:
        self.records: list[ToolCallRecord] = []
        self._sequence = 0

    async def next_ref(self, context: ToolContext) -> str:
        self._sequence += 1
        return f"T{self._sequence}"

    async def record(self, record: ToolCallRecord) -> None:
        self.records.append(record)


class DatabaseToolCallRecorder:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def next_ref(self, context: ToolContext) -> str:
        async with transaction(self._sessions) as session:
            sequence = await session.scalar(
                update(Incident)
                .where(Incident.id == context.incident_id)
                .values(tool_call_seq=Incident.tool_call_seq + 1)
                .returning(Incident.tool_call_seq)
            )
        return f"T{sequence}"

    async def record(self, record: ToolCallRecord) -> None:
        async with transaction(self._sessions) as session:
            session.add(
                ToolCall(
                    ref=record.ref,
                    incident_id=record.context.incident_id,
                    agent=record.context.agent,
                    tool=record.tool,
                    args=record.args,
                    permission=record.permission,
                    decision=record.decision,
                    decision_reason=record.decision_reason,
                    ok=record.ok,
                    started_at=record.started_at,
                    duration_ms=record.duration_ms,
                    result=record.result,
                    result_text=record.result_text,
                    result_sha256=record.result_sha256(),
                    truncated=record.truncated,
                    injection_flags=record.injection_flags,
                )
            )
