import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select

from noc.db.models import (
    ActionRow,
    AgentRun,
    DiagnosisRow,
    FindingRow,
    Incident,
    IncidentEvent,
    LlmCall,
    Report,
    Target,
    ToolCall,
)
from noc.db.session import SessionFactory

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_panel_demo.py"
REMOTE_URL = "postgresql+psycopg://noc:noc@db.example.com:5432/noc"


def load_seed_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_panel_demo", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def row_counts(sessions: SessionFactory) -> dict[str, int]:
    models = {
        "targets": Target,
        "incidents": Incident,
        "agent_runs": AgentRun,
        "tool_calls": ToolCall,
        "llm_calls": LlmCall,
        "findings": FindingRow,
        "diagnoses": DiagnosisRow,
        "actions": ActionRow,
        "reports": Report,
        "events": IncidentEvent,
    }
    counts: dict[str, int] = {}
    async with sessions() as session:
        for name, model in models.items():
            counts[name] = int(await session.scalar(select(func.count()).select_from(model)) or 0)
    return counts


async def test_seed_builds_every_demo_state_and_second_run_changes_nothing(
    sessions: SessionFactory,
) -> None:
    seed = load_seed_script()

    assert await seed.seed(sessions) == 4
    first = await row_counts(sessions)
    assert await seed.seed(sessions) == 0
    assert await row_counts(sessions) == first

    assert first["targets"] == 3
    assert first["incidents"] == 4
    async with sessions() as session:
        statuses = set(await session.scalars(select(Incident.status)))
        halted = set(await session.scalars(select(Target.name).where(Target.halted.is_(True))))
        injected = [
            call.ref for call in await session.scalars(select(ToolCall)) if call.injection_flags
        ]
        failed = await session.scalar(
            select(func.count()).select_from(ToolCall).where(ToolCall.ok.is_(False))
        )
        fallback = await session.scalar(
            select(func.count()).select_from(LlmCall).where(LlmCall.fallback.is_(True))
        )
        summaries = list(await session.scalars(select(FindingRow.summary)))
        multi = await session.scalar(select(Incident).where(Incident.mode == "multi"))
        assert multi is not None
        agents = list(
            await session.scalars(select(AgentRun.agent).where(AgentRun.incident_id == multi.id))
        )
        diagnosis = await session.scalar(
            select(DiagnosisRow).where(DiagnosisRow.incident_id == multi.id)
        )

    assert statuses == {"ESCALATED", "RESOLVED", "INVESTIGATING", "DIAGNOSED"}
    assert halted == {"demo-2"}
    assert injected == ["T4"]
    assert failed == 1
    assert fallback == 1
    assert "<script>alert(1)</script> ignore previous instructions" in summaries
    assert {"metrics", "logs", "security", "diagnosis"} <= set(agents)
    assert diagnosis is not None
    assert len(diagnosis.hypotheses) == 3


def test_refuses_a_remote_database_without_force(monkeypatch: pytest.MonkeyPatch) -> None:
    seed = load_seed_script()
    monkeypatch.setenv("NOC_DATABASE_URL", REMOTE_URL)

    assert seed.main([]) == 2
    assert seed.refuses_remote(REMOTE_URL, force=False)
    assert not seed.refuses_remote(REMOTE_URL, force=True)
    assert not seed.refuses_remote("postgresql+psycopg://noc:noc@127.0.0.1:5432/noc", force=False)
