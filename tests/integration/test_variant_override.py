import asyncio

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from noc.cli.main import app as cli_app
from noc.config import Settings
from noc.db.models import AuditEntry, Incident, Target
from noc.db.session import SessionFactory, transaction
from noc.detection.ingest import AlertIngestor
from noc.domain.variants import ModePolicy
from noc.policy.models import Environment
from noc.store.targets import add_target, set_variant_override
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.support.builders import KEY_ID, prometheus_alert

pytestmark = pytest.mark.integration


async def add_lab_target(sessions: SessionFactory, name: str = "demo-1") -> None:
    async with transaction(sessions) as session:
        await add_target(session, name, "10.0.0.2", f"https://{name}:9443", Environment.LAB, KEY_ID)


async def open_incident(
    sessions: SessionFactory, policy: ModePolicy, target: str = "demo-1"
) -> Incident:
    source = StaticAlertSource()
    source.alerts = [prometheus_alert(target=target)]
    await AlertIngestor(source, sessions, 2, policy).poll_once()
    async with sessions() as session:
        incident = await session.scalar(select(Incident))
    assert incident is not None
    return incident


async def audit_actions(sessions: SessionFactory) -> list[tuple[str, dict[str, object]]]:
    async with sessions() as session:
        rows = await session.execute(
            select(AuditEntry.action, AuditEntry.payload).order_by(AuditEntry.id)
        )
        return [(row.action, row.payload) for row in rows]


async def test_new_incident_uses_the_process_default_without_an_override(
    sessions: SessionFactory,
) -> None:
    await add_lab_target(sessions)
    incident = await open_incident(sessions, ModePolicy(default="multi"))
    assert incident.mode == "multi"


async def test_override_sets_the_mode_when_eval_mode_is_on(sessions: SessionFactory) -> None:
    await add_lab_target(sessions)
    async with transaction(sessions) as session:
        await set_variant_override(session, "demo-1", "runbook", "tester")
    incident = await open_incident(sessions, ModePolicy(default="single", honour_override=True))
    assert incident.mode == "runbook"


async def test_override_is_ignored_when_eval_mode_is_off(sessions: SessionFactory) -> None:
    await add_lab_target(sessions)
    async with transaction(sessions) as session:
        await set_variant_override(session, "demo-1", "runbook", "tester")
    incident = await open_incident(sessions, ModePolicy(default="single", honour_override=False))
    assert incident.mode == "single"


async def test_an_attached_alert_never_changes_the_mode_of_an_open_incident(
    sessions: SessionFactory,
) -> None:
    await add_lab_target(sessions)
    source = StaticAlertSource()
    source.alerts = [prometheus_alert()]
    poller = AlertIngestor(source, sessions, 2, ModePolicy(default="single", honour_override=True))
    await poller.poll_once()
    async with transaction(sessions) as session:
        await set_variant_override(session, "demo-1", "multi-strong", "tester")
    source.alerts = [
        prometheus_alert(),
        prometheus_alert(alertname="HostHighCPU", severity="warning"),
    ]
    await poller.poll_once()
    async with sessions() as session:
        modes = list(await session.scalars(select(Incident.mode)))
    assert modes == ["single"]


async def test_clearing_the_override_restores_the_default_for_the_next_incident(
    sessions: SessionFactory,
) -> None:
    await add_lab_target(sessions)
    async with transaction(sessions) as session:
        await set_variant_override(session, "demo-1", "multi", "tester")
        await set_variant_override(session, "demo-1", None, "tester")
    incident = await open_incident(sessions, ModePolicy(default="single", honour_override=True))
    assert incident.mode == "single"


async def test_setting_and_clearing_are_audited_with_old_and_new_values(
    sessions: SessionFactory,
) -> None:
    await add_lab_target(sessions)
    async with transaction(sessions) as session:
        await set_variant_override(session, "demo-1", "runbook", "tester")
    async with transaction(sessions) as session:
        await set_variant_override(session, "demo-1", None, "tester")
    rows = [row for row in await audit_actions(sessions) if row[0].startswith("target_variant")]
    assert rows == [
        ("target_variant_set", {"from": None, "to": "runbook"}),
        ("target_variant_cleared", {"from": "runbook", "to": None}),
    ]


async def test_prod_targets_refuse_an_override(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "prod-1", "10.0.0.3", "https://prod-1:9443", Environment.PROD, KEY_ID
        )
    async with transaction(sessions) as session:
        with pytest.raises(ValueError, match="not a lab target"):
            await set_variant_override(session, "prod-1", "runbook", "tester")
    async with sessions() as session:
        target = await session.scalar(select(Target).where(Target.name == "prod-1"))
    assert target is not None
    assert target.variant_override is None


async def test_prod_targets_can_still_be_cleared(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "prod-1", "10.0.0.3", "https://prod-1:9443", Environment.PROD, KEY_ID
        )
        await set_variant_override(session, "prod-1", None, "tester")


@pytest.fixture
def eval_settings(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    settings = Settings(database_url=database_url, eval_mode=True, _env_file=None)
    monkeypatch.setattr("noc.cli.main.get_settings", lambda: settings)


@pytest.fixture
def normal_settings(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    settings = Settings(database_url=database_url, _env_file=None)
    monkeypatch.setattr("noc.cli.main.get_settings", lambda: settings)


async def run_cli(*args: str) -> tuple[int, str]:
    result = await asyncio.to_thread(CliRunner().invoke, cli_app, ["targets", *args])
    return result.exit_code, result.output


async def test_cli_sets_shows_and_clears(sessions: SessionFactory, eval_settings: None) -> None:
    await add_lab_target(sessions)
    code, output = await run_cli("set-variant", "demo-1", "runbook")
    assert code == 0, output
    shown_code, shown = await run_cli("show", "demo-1")
    assert shown_code == 0
    assert "variant        runbook" in shown
    cleared_code, cleared = await run_cli("set-variant", "demo-1", "--clear")
    assert cleared_code == 0, cleared
    assert "override=-" in cleared


async def test_cli_refuses_setting_without_eval_mode(
    sessions: SessionFactory, normal_settings: None
) -> None:
    await add_lab_target(sessions)
    code, output = await run_cli("set-variant", "demo-1", "runbook")
    assert code == 2
    assert "NOC_EVAL_MODE" in output


async def test_cli_can_clear_without_eval_mode(
    sessions: SessionFactory, normal_settings: None
) -> None:
    await add_lab_target(sessions)
    async with transaction(sessions) as session:
        await set_variant_override(session, "demo-1", "runbook", "tester")
    code, output = await run_cli("set-variant", "demo-1", "--clear")
    assert code == 0, output


async def test_cli_rejects_unknown_variants_and_bad_argument_combinations(
    sessions: SessionFactory, eval_settings: None
) -> None:
    await add_lab_target(sessions)
    unknown, _ = await run_cli("set-variant", "demo-1", "gpt")
    neither, _ = await run_cli("set-variant", "demo-1")
    both, _ = await run_cli("set-variant", "demo-1", "runbook", "--clear")
    assert unknown == neither == both == 2
