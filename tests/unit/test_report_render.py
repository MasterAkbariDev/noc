import uuid
from datetime import UTC, datetime

from noc.db.models import ActionRow, AlertEvent, DiagnosisRow, FindingRow, Incident, Target
from noc.reporting.builder import CostSummary, ReportData, render_report

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def test_report_contains_every_section_and_db_numbers() -> None:
    target = Target(name="demo-1", environment="lab", automation_level="auto_safe")
    incident = Incident(
        id=uuid.uuid4(),
        title="ServiceDown on demo-1/svc:demo-shop",
        status="ESCALATED",
        escalation_reason="execution_not_available",
        severity="critical",
        opened_at=NOW,
    )
    data = ReportData(
        incident=incident,
        target=target,
        alerts=[
            AlertEvent(
                alertname="ServiceDown",
                severity="critical",
                labels={"resource": "svc:demo-shop"},
                state="firing",
                starts_at=NOW,
            )
        ],
        findings=[
            FindingRow(
                label="F1",
                category="service",
                severity="critical",
                summary="unit failed",
                evidence=[{"tool_call_ref": "T1", "excerpt": "failed"}],
                suspected_injection=False,
            )
        ],
        diagnosis=DiagnosisRow(
            primary_code="service_crashed",
            confidence=0.9,
            hypotheses=[
                {
                    "root_cause_code": "service_crashed",
                    "confidence": 0.9,
                    "supporting_findings": ["F1"],
                    "contradicting_findings": [],
                    "description": "died",
                }
            ],
            ungrounded_findings=0,
        ),
        actions=[
            ActionRow(
                action_type="restart_service",
                resource_id="svc:demo-shop",
                permission_class="BLOCKED",
                eligible=False,
                impact_score=20,
                gate_failures=["execution_disabled"],
                reasons=[],
            )
        ],
        events=[],
        cost=CostSummary(
            llm_calls=3, tokens_in=1200, tokens_out=300, tool_calls=1, providers=["gemini"]
        ),
    )
    markdown = render_report(data)
    for expected in (
        "## Alerts",
        "## Findings",
        "`service_crashed` (confidence 0.90)",
        "execution_disabled",
        "LLM calls: 3 (providers: gemini)",
        "Tokens: 1200 in / 300 out",
    ):
        assert expected in markdown
