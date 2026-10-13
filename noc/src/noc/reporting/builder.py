import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.models import (
    ActionRow,
    AlertEvent,
    DiagnosisRow,
    FindingRow,
    Incident,
    IncidentEvent,
    LlmCall,
    Target,
    ToolCall,
)


@dataclass(frozen=True)
class CostSummary:
    llm_calls: int
    tokens_in: int
    tokens_out: int
    tool_calls: int
    providers: list[str]


@dataclass(frozen=True)
class ReportData:
    incident: Incident
    target: Target
    alerts: list[AlertEvent]
    findings: list[FindingRow]
    diagnosis: DiagnosisRow | None
    actions: list[ActionRow]
    events: list[IncidentEvent]
    cost: CostSummary


async def load_cost(session: AsyncSession, incident_id: uuid.UUID) -> CostSummary:
    llm_calls, tokens_in, tokens_out, providers = (
        await session.execute(
            select(
                func.count(LlmCall.id),
                func.coalesce(func.sum(LlmCall.tokens_in), 0),
                func.coalesce(func.sum(LlmCall.tokens_out), 0),
                func.array_agg(func.distinct(LlmCall.provider)),
            ).where(LlmCall.incident_id == incident_id)
        )
    ).one()
    tool_calls = await session.scalar(
        select(func.count(ToolCall.id)).where(ToolCall.incident_id == incident_id)
    )
    return CostSummary(
        llm_calls=llm_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tool_calls=tool_calls or 0,
        providers=sorted(provider for provider in (providers or []) if provider),
    )


async def load_report_data(session: AsyncSession, incident_id: uuid.UUID) -> ReportData:
    incident = await session.get_one(Incident, incident_id)
    target = await session.get_one(Target, incident.target_id)
    alerts = await session.scalars(
        select(AlertEvent)
        .where(AlertEvent.incident_id == incident_id)
        .order_by(AlertEvent.starts_at)
    )
    findings = await session.scalars(
        select(FindingRow).where(FindingRow.incident_id == incident_id).order_by(FindingRow.label)
    )
    diagnosis = await session.scalar(
        select(DiagnosisRow)
        .where(DiagnosisRow.incident_id == incident_id)
        .order_by(DiagnosisRow.created_at.desc())
        .limit(1)
    )
    actions = await session.scalars(
        select(ActionRow).where(ActionRow.incident_id == incident_id).order_by(ActionRow.created_at)
    )
    events = await session.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.id)
    )
    return ReportData(
        incident=incident,
        target=target,
        alerts=list(alerts),
        findings=list(findings),
        diagnosis=diagnosis,
        actions=list(actions),
        events=list(events),
        cost=await load_cost(session, incident_id),
    )


def table(headers: list[str], body: list[list[str]]) -> list[str]:
    if not body:
        return ["_none_"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in body]
    return lines


def render_report(data: ReportData) -> str:
    incident, target = data.incident, data.target
    lines = [
        f"# Incident report — {incident.title}",
        "",
        f"- **Incident:** `{incident.id}`  ",
        f"- **Target:** {target.name} ({target.environment}, "
        f"automation: {target.automation_level})",
        f"- **Status:** {incident.status}"
        + (f" ({incident.escalation_reason})" if incident.escalation_reason else ""),
        f"- **Severity:** {incident.severity}",
        f"- **Opened:** {incident.opened_at.isoformat()}",
        "",
        "## Alerts",
        *table(
            ["Alert", "Severity", "Resource", "State", "Since"],
            [
                [
                    a.alertname,
                    a.severity,
                    a.labels.get("resource", "-"),
                    a.state,
                    a.starts_at.isoformat(),
                ]
                for a in data.alerts
            ],
        ),
        "",
        "## Findings (grounded evidence only)",
        *table(
            ["Id", "Category", "Severity", "Summary", "Evidence", "Injection?"],
            [
                [
                    f.label,
                    f.category,
                    f.severity,
                    f.summary,
                    ", ".join(e["tool_call_ref"] for e in f.evidence),
                    "yes" if f.suspected_injection else "no",
                ]
                for f in data.findings
            ],
        ),
        "",
        "## Diagnosis",
    ]
    if data.diagnosis is None:
        lines.append("_No diagnosis was produced._")
    else:
        lines += [
            f"**Root cause:** `{data.diagnosis.primary_code}` "
            f"(confidence {data.diagnosis.confidence:.2f})",
            "",
            *table(
                ["Code", "Confidence", "Supported by", "Contradicted by", "Description"],
                [
                    [
                        h["root_cause_code"],
                        f"{h['confidence']:.2f}",
                        ", ".join(h["supporting_findings"]) or "-",
                        ", ".join(h["contradicting_findings"]) or "-",
                        h["description"],
                    ]
                    for h in data.diagnosis.hypotheses
                ],
            ),
        ]
        if data.diagnosis.ungrounded_findings:
            lines.append(
                f"\n{data.diagnosis.ungrounded_findings} finding(s) were dropped "
                "by the grounding check."
            )
    lines += [
        "",
        actions_heading(data.actions),
        *table(
            ["Action", "Resource", "Class", "Status", "Authorized by", "Result", "Gates failed"],
            [
                [
                    a.action_type,
                    a.resource_id or "-",
                    a.permission_class,
                    a.status or "-",
                    a.authorization or "-",
                    a.result_code or ("ok" if a.status == "succeeded" else "-"),
                    ", ".join(a.gate_failures) or "-",
                ]
                for a in data.actions
            ],
        ),
        "",
        "## Timeline",
        *table(
            ["Time", "Event", "Actor", "Details"],
            [[e.ts.isoformat(), e.type, e.actor, compact(e.payload)] for e in data.events],
        ),
        "",
        "## Cost",
        f"- LLM calls: {data.cost.llm_calls} (providers: {', '.join(data.cost.providers) or '-'})",
        f"- Tokens: {data.cost.tokens_in} in / {data.cost.tokens_out} out",
        f"- Tool calls: {data.cost.tool_calls}",
        "",
    ]
    return "\n".join(lines)


EXECUTED_ACTION_STATUSES = frozenset({"dispatched", "succeeded", "failed", "outcome_unknown"})


def actions_heading(actions: list[ActionRow]) -> str:
    if any(action.status in EXECUTED_ACTION_STATUSES for action in actions):
        return "## Actions"
    return "## Policy decisions (no action was executed)"


def compact(payload: dict[str, object]) -> str:
    return ", ".join(f"{key}={value}" for key, value in payload.items() if value is not None)
