import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select

from noc.auth.passwords import verify_password
from noc.db.models import (
    ActionRow,
    AgentRun,
    DiagnosisRow,
    FindingRow,
    FleetHost,
    Incident,
    IncidentEvent,
    LlmCall,
    Report,
    SshKey,
    SshKeyInstall,
    Target,
    ToolCall,
    User,
)
from noc.db.session import SessionFactory

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_panel_demo.py"
REMOTE_URL = "postgresql+psycopg://noc:noc@db.example.com:5432/noc"
LOCAL_URL = "postgresql+psycopg://noc:noc@127.0.0.1:5432/noc"
FIRST_PASSWORD = "first e2e password"
SECOND_PASSWORD = "second e2e password"
E2E_ROLES = {"e2e-admin": "admin", "e2e-operator": "operator", "e2e-viewer": "viewer"}


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

    assert await seed.seed(sessions) == 6
    first = await row_counts(sessions)
    assert await seed.seed(sessions) == 0
    assert await row_counts(sessions) == first

    assert first["targets"] == 4
    assert first["incidents"] == 6
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

    assert statuses == {
        "ESCALATED",
        "RESOLVED",
        "INVESTIGATING",
        "DIAGNOSED",
        "AWAITING_APPROVAL",
    }
    assert halted == {"demo-2"}
    assert injected == ["T4"]
    assert failed == 1
    assert fallback == 1
    assert "<script>alert(1)</script> ignore previous instructions" in summaries
    assert {"metrics", "logs", "security", "diagnosis"} <= set(agents)
    assert diagnosis is not None
    assert len(diagnosis.hypotheses) == 3


async def test_seeded_approvals_are_one_fresh_and_one_already_expired(
    sessions: SessionFactory,
) -> None:
    seed = load_seed_script()
    await seed.seed(sessions)

    async with sessions() as session:
        waiting = await session.scalar(
            select(Incident).where(Incident.title == seed.AWAITING_TITLE)
        )
        expired = await session.scalar(select(Incident).where(Incident.title == seed.EXPIRED_TITLE))
        assert waiting is not None
        assert expired is not None
        pending = list(
            await session.scalars(select(ActionRow).where(ActionRow.status == "pending_approval"))
        )
        requested = await session.scalar(
            select(func.count())
            .select_from(IncidentEvent)
            .where(IncidentEvent.type == "approval_requested")
        )

    assert waiting.status == "AWAITING_APPROVAL"
    assert expired.status == "AWAITING_APPROVAL"
    expiry_by_incident = {action.incident_id: action.approval_expires_at for action in pending}
    assert set(expiry_by_incident) == {waiting.id, expired.id}
    now = datetime.now(UTC)
    fresh = expiry_by_incident[waiting.id]
    assert fresh is not None
    assert timedelta(minutes=59) < fresh - now <= timedelta(hours=1, minutes=1)
    past = expiry_by_incident[expired.id]
    assert past is not None
    assert past < now
    assert requested == 2


def test_refuses_a_remote_database_without_force(monkeypatch: pytest.MonkeyPatch) -> None:
    seed = load_seed_script()
    monkeypatch.setenv("NOC_DATABASE_URL", REMOTE_URL)

    assert seed.main([]) == 2
    assert seed.refuses_remote(REMOTE_URL, force=False)
    assert not seed.refuses_remote(REMOTE_URL, force=True)
    assert not seed.refuses_remote("postgresql+psycopg://noc:noc@127.0.0.1:5432/noc", force=False)


def test_e2e_password_must_be_at_least_twelve_characters() -> None:
    seed = load_seed_script()

    assert seed.e2e_password({"NOC_E2E_PASSWORD": "x" * 11}) is None
    assert seed.e2e_password({}) is None
    assert seed.e2e_password({"NOC_E2E_PASSWORD": "x" * 12}) == "x" * 12


def test_with_users_refuses_a_missing_or_short_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed = load_seed_script()
    monkeypatch.setenv("NOC_DATABASE_URL", LOCAL_URL)
    monkeypatch.delenv("NOC_E2E_PASSWORD", raising=False)

    assert seed.main(["--with-users"]) == 2

    monkeypatch.setenv("NOC_E2E_PASSWORD", "short-pass")
    assert seed.main(["--with-users"]) == 2
    captured = capsys.readouterr()
    assert "NOC_E2E_PASSWORD must be set" in captured.err
    assert "short-pass" not in captured.out + captured.err


async def test_with_users_creates_three_roles_and_a_rerun_resets_the_password(
    sessions: SessionFactory, database_url: str
) -> None:
    seed = load_seed_script()

    await seed.run(database_url, FIRST_PASSWORD)
    async with sessions() as session:
        first_ids = {user.username: user.id for user in await session.scalars(select(User))}
        roles = {user.username: user.role for user in await session.scalars(select(User))}
    assert roles == E2E_ROLES

    await seed.run(database_url, SECOND_PASSWORD)
    async with sessions() as session:
        users = {user.username: user for user in await session.scalars(select(User))}
    assert {name: user.id for name, user in users.items()} == first_ids
    admin = users["e2e-admin"]
    assert verify_password(admin.password_hash, SECOND_PASSWORD)
    assert not verify_password(admin.password_hash, FIRST_PASSWORD)


async def test_fleet_seed_adds_hosts_and_keys_once(
    sessions: SessionFactory, tmp_path: Path
) -> None:
    seed = load_seed_script()
    await seed.seed(sessions)
    store = seed.SecretStore(tmp_path / "secrets")

    assert await seed.seed_fleet(sessions, store) is True
    assert await seed.seed_fleet(sessions, store) is False

    async with sessions() as session:
        hosts = set(await session.scalars(select(FleetHost.name)))
        keys = list(await session.scalars(select(SshKey)))
        installs = int(await session.scalar(select(func.count()).select_from(SshKeyInstall)) or 0)
    assert hosts == {"demo-1", "web-5"}
    assert len(keys) == 5
    assert {key.environment for key in keys} == {"lab", "prod"}
    assert sum(key.replaces_id is not None for key in keys) == 1
    assert installs == 3
    assert all(store.read(f"ssh-key-{key.id}") is not None for key in keys)
