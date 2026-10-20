"""The Telegram bot's second panel: menus, incident and approval screens.

Rendering is pure. Loaders read the database and return plain rows; decisions reuse the panel's
own approval code, so the bot checks the same things the panel does.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.models import ActionRow, Incident, LlmKeyStatus, Target
from noc.domain.incident_status import ACTIVE_STATUSES, IncidentStatus
from noc.notify.telegram import Button, Keyboard
from noc.store.remediation import (
    PENDING_APPROVAL,
    ApprovalConflict,
    ApprovalDecision,
    record_approval,
)

PRODUCTION: Final = "prod"
PROD_NEEDS_PANEL: Final = (
    "Production approvals need a second-factor code. Approve this one in the panel."
)
STATUS_ICON: Final[dict[str, str]] = {
    "NEW": "🆕",
    "INVESTIGATING": "🔎",
    "DIAGNOSED": "🧩",
    "PLANNED": "📋",
    "REMEDIATING": "🔧",
    "AWAITING_APPROVAL": "⏳",
    "VERIFYING": "🧪",
    "ESCALATED": "🚨",
    "RESOLVED": "✅",
    "SELF_RESOLVED": "✅",
    "CLOSED": "🔒",
}
AUTOMATION_ICON: Final[dict[str, str]] = {
    "auto_safe": "🟢 auto for safe fixes",
    "approval_required": "🟡 needs approval",
    "observe_only": "👁 observe only",
}
KEY_ICON: Final[dict[str, str]] = {"ok": "🟢", "cooling": "🟠", "rejected": "⛔"}
MENU_BACK: Final = Button(text="⬅️ Menu", callback_data="m:home")
MENU_ROW_LIMIT: Final = 10


@dataclass(frozen=True)
class Overview:
    active: int
    escalated: int
    pending: int
    targets: int
    halted: int
    keys_ok: int
    keys_total: int


@dataclass(frozen=True)
class IncidentRow:
    id: uuid.UUID
    title: str
    status: str
    reason: str | None
    root_cause: str | None
    confidence: float | None
    target: str
    opened_at: datetime


@dataclass(frozen=True)
class ApprovalRow:
    action_id: uuid.UUID
    incident_id: uuid.UUID
    incident_title: str
    action_type: str
    resource_id: str
    target: str
    environment: str
    impact: int
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TargetRow:
    name: str
    environment: str
    automation: str
    halted: bool
    active_incident: str | None


@dataclass(frozen=True)
class KeyRow:
    label: str
    provider: str
    state: str
    last_error: str | None
    last_success_at: datetime | None


def open_in_panel(panel_url: str, path: str) -> list[Button]:
    return [Button(text="🌐 Open in panel", url=f"{panel_url}{path}")] if panel_url else []


def back_row(panel_url: str, path: str = "/") -> list[Button]:
    return [*open_in_panel(panel_url, path), MENU_BACK]


def with_back(keyboard: Keyboard, panel_url: str = "", path: str = "/") -> Keyboard:
    return [*keyboard, back_row(panel_url, path)]


def main_menu(panel_url: str) -> tuple[str, Keyboard]:
    keyboard: Keyboard = [
        [
            Button(text="📊 Overview", callback_data="m:overview"),
            Button(text="🚨 Incidents", callback_data="m:incidents"),
        ],
        [
            Button(text="✅ Approvals", callback_data="m:approvals"),
            Button(text="🖥 Servers", callback_data="m:servers"),
        ],
        [
            Button(text="🧠 Models", callback_data="m:models"),
            Button(text="⚙️ Settings", callback_data="m:settings"),
        ],
        [Button(text="❓ Help", callback_data="m:help")],
    ]
    if panel_url:
        keyboard.append([Button(text="🌐 Open the panel", url=panel_url)])
    return "🛰 NOC control\nPick a section below.", keyboard


def render_overview(overview: Overview, panel_url: str) -> tuple[str, Keyboard]:
    text = "\n".join(
        [
            "📊 Overview",
            f"🔎 Active incidents: {overview.active}",
            f"🚨 Escalated to a person: {overview.escalated}",
            f"⏳ Waiting for your approval: {overview.pending}",
            f"🖥 Servers: {overview.targets} ({overview.halted} halted)",
            f"🧠 Model keys working: {overview.keys_ok} of {overview.keys_total}",
        ]
    )
    return text, with_back([[Button(text="🚨 Incidents", callback_data="m:incidents")]], panel_url)


def render_incidents(rows: list[IncidentRow], panel_url: str) -> tuple[str, Keyboard]:
    if not rows:
        return "🚨 No incidents yet.", with_back([])
    lines = ["🚨 Incidents, active first"]
    keyboard: Keyboard = []
    for row in rows[:MENU_ROW_LIMIT]:
        icon = STATUS_ICON.get(row.status, "❔")
        lines.append(f"{icon} {row.title} · {row.status.lower()}")
        keyboard.append([Button(text=f"{icon} {row.title}"[:60], callback_data=f"i:{row.id}")])
    return "\n".join(lines), with_back(keyboard, panel_url)


def render_approvals(rows: list[ApprovalRow]) -> tuple[str, Keyboard]:
    if not rows:
        return "✅ Nothing is waiting for approval.", with_back([])
    lines = ["⏳ Waiting for your approval"]
    keyboard: Keyboard = []
    for row in rows[:MENU_ROW_LIMIT]:
        lines.append(f"• {row.action_type} on {row.resource_id} ({row.target})")
        keyboard.append(
            [
                Button(
                    text=f"🔎 {row.action_type} · {row.target}"[:60],
                    callback_data=f"a:{row.action_id}",
                )
            ]
        )
    return "\n".join(lines), with_back(keyboard)


def render_approval(row: ApprovalRow, panel_url: str) -> tuple[str, Keyboard]:
    reasons = ", ".join(row.reasons) if row.reasons else "policy wants a person to check"
    text = "\n".join(
        [
            f"🔧 {row.action_type} on {row.resource_id}",
            f"Server: {row.target} ({row.environment})",
            f"Incident: {row.incident_title}",
            f"Impact score: {row.impact}",
            f"Why it waits: {reasons}",
        ]
    )
    keyboard: Keyboard = [
        [
            Button(text="✅ Approve", callback_data=f"y:{row.action_id}"),
            Button(text="⛔ Reject", callback_data=f"do:no:{row.action_id}"),
        ]
    ]
    return text, with_back(keyboard, panel_url, f"/incidents/{row.incident_id}")


def render_confirm(row: ApprovalRow) -> tuple[str, Keyboard]:
    text = (
        f"Approve {row.action_type} on {row.resource_id} on {row.target}?\n"
        "It runs right away once you confirm."
    )
    keyboard: Keyboard = [
        [
            Button(text="✅ Yes, approve", callback_data=f"do:ok:{row.action_id}"),
            Button(text="✖ Cancel", callback_data=f"a:{row.action_id}"),
        ]
    ]
    return text, keyboard


def render_close_confirm(row: IncidentRow) -> tuple[str, Keyboard]:
    text = (
        f"Close {row.title} as handled?\n"
        "NOC stops working on it. Use the panel to record a root cause."
    )
    keyboard: Keyboard = [
        [
            Button(text="🔒 Yes, close", callback_data=f"do:cl:{row.id}"),
            Button(text="✖ Cancel", callback_data=f"i:{row.id}"),
        ]
    ]
    return text, keyboard


def render_servers(rows: list[TargetRow]) -> tuple[str, Keyboard]:
    if not rows:
        return "🖥 No servers are registered.", with_back([])
    lines = ["🖥 Servers"]
    for row in rows:
        state = "⛔ halted" if row.halted else AUTOMATION_ICON.get(row.automation, row.automation)
        busy = f" · 🔎 {row.active_incident}" if row.active_incident else ""
        lines.append(f"• {row.name} ({row.environment}): {state}{busy}")
    return "\n".join(lines), with_back([])


def render_models(rows: list[KeyRow]) -> tuple[str, Keyboard]:
    if not rows:
        return "🧠 No model keys are configured.", with_back([])
    lines = ["🧠 Model keys"]
    for row in rows:
        icon = KEY_ICON.get(row.state, "⚪")
        error = f" · last error: {row.last_error}" if row.last_error and row.state != "ok" else ""
        lines.append(f"{icon} {row.provider} {row.label}: {row.state}{error}")
    return "\n".join(lines), with_back([])


def render_help() -> tuple[str, Keyboard]:
    text = "\n".join(
        [
            "❓ How to use this bot",
            "Use the buttons. /menu brings the menu back.",
            "🚨 Incidents shows what NOC is handling and what it fixed.",
            "✅ Approvals lists fixes that wait for a person. Approve or reject them here.",
            "🖥 Servers and 🧠 Models show their state.",
            "⚙️ Settings chooses which messages you get.",
            "Commands still work too: /status, /admins, /add, /remove, /mute, /pause, /test.",
        ]
    )
    return text, with_back([])


def active_values() -> list[str]:
    return [status.value for status in ACTIVE_STATUSES]


async def load_overview(session: AsyncSession) -> Overview:
    statuses = list(
        await session.scalars(select(Incident.status).where(Incident.status.in_(active_values())))
    )
    escalated = await session.scalar(
        select(func.count())
        .select_from(Incident)
        .where(Incident.status == IncidentStatus.ESCALATED.value)
    )
    pending = await session.scalar(
        select(func.count()).select_from(ActionRow).where(ActionRow.status == PENDING_APPROVAL)
    )
    targets = list(await session.scalars(select(Target)))
    keys = list(await session.scalars(select(LlmKeyStatus)))
    return Overview(
        active=len(statuses),
        escalated=int(escalated or 0),
        pending=int(pending or 0),
        targets=len(targets),
        halted=sum(1 for target in targets if target.halted),
        keys_ok=sum(1 for key in keys if key.state == "ok"),
        keys_total=len(keys),
    )


async def load_incidents(session: AsyncSession) -> list[IncidentRow]:
    rows = (
        await session.execute(
            select(Incident, Target.name)
            .join(Target, Target.id == Incident.target_id)
            .order_by(Incident.opened_at.desc())
            .limit(40)
        )
    ).all()
    active = set(active_values())
    ordered = sorted(rows, key=lambda row: row[0].status not in active)
    return [incident_row(incident, name) for incident, name in ordered[:MENU_ROW_LIMIT]]


def incident_row(incident: Incident, target_name: str) -> IncidentRow:
    return IncidentRow(
        id=incident.id,
        title=incident.title,
        status=incident.status,
        reason=incident.escalation_reason,
        root_cause=incident.root_cause_code,
        confidence=incident.confidence,
        target=target_name,
        opened_at=incident.opened_at,
    )


async def load_incident(session: AsyncSession, incident_id: uuid.UUID) -> IncidentRow | None:
    found = (
        await session.execute(
            select(Incident, Target.name)
            .join(Target, Target.id == Incident.target_id)
            .where(Incident.id == incident_id)
        )
    ).first()
    return None if found is None else incident_row(found[0], found[1])


async def pending_action_of(session: AsyncSession, incident_id: uuid.UUID) -> uuid.UUID | None:
    return await session.scalar(
        select(ActionRow.id)
        .where(ActionRow.incident_id == incident_id, ActionRow.status == PENDING_APPROVAL)
        .limit(1)
    )


def approval_row(
    action: ActionRow, incident_title: str, target_name: str, environment: str
) -> ApprovalRow:
    return ApprovalRow(
        action_id=action.id,
        incident_id=action.incident_id,
        incident_title=incident_title,
        action_type=action.action_type,
        resource_id=action.resource_id or "the server",
        target=target_name,
        environment=environment,
        impact=action.impact_score,
        reasons=list(action.reasons or []),
    )


async def load_approvals(session: AsyncSession) -> list[ApprovalRow]:
    rows = (
        await session.execute(
            select(ActionRow, Incident.title, Target.name, Target.environment)
            .join(Incident, Incident.id == ActionRow.incident_id)
            .join(Target, Target.id == ActionRow.target_id)
            .where(ActionRow.status == PENDING_APPROVAL)
            .order_by(ActionRow.created_at)
        )
    ).all()
    return [approval_row(action, title, name, env) for action, title, name, env in rows]


async def load_approval(session: AsyncSession, action_id: uuid.UUID) -> ApprovalRow | None:
    found = (
        await session.execute(
            select(ActionRow, Incident.title, Target.name, Target.environment)
            .join(Incident, Incident.id == ActionRow.incident_id)
            .join(Target, Target.id == ActionRow.target_id)
            .where(ActionRow.id == action_id, ActionRow.status == PENDING_APPROVAL)
        )
    ).first()
    return None if found is None else approval_row(found[0], found[1], found[2], found[3])


async def load_servers(session: AsyncSession) -> list[TargetRow]:
    targets = list(await session.scalars(select(Target).order_by(Target.name)))
    busy = dict(
        (
            await session.execute(
                select(Incident.target_id, Incident.title).where(
                    Incident.status.in_(active_values())
                )
            )
        ).all()
    )
    return [
        TargetRow(
            name=target.name,
            environment=target.environment,
            automation=target.automation_level,
            halted=target.halted,
            active_incident=busy.get(target.id),
        )
        for target in targets
    ]


async def load_keys(session: AsyncSession) -> list[KeyRow]:
    rows = list(
        await session.scalars(
            select(LlmKeyStatus).order_by(LlmKeyStatus.provider, LlmKeyStatus.label)
        )
    )
    return [
        KeyRow(
            label=row.label,
            provider=row.provider,
            state=row.state,
            last_error=row.last_error,
            last_success_at=row.last_success_at,
        )
        for row in rows
    ]


async def decide(
    session: AsyncSession, action_id: uuid.UUID, decision: ApprovalDecision, actor: str
) -> str:
    action = await session.get(ActionRow, action_id)
    if action is None or action.status != PENDING_APPROVAL:
        return "That fix is no longer waiting for an approval."
    target = await session.get_one(Target, action.target_id)
    if target.environment == PRODUCTION:
        return PROD_NEEDS_PANEL
    try:
        await record_approval(
            session, action.incident_id, action.id, decision, actor, action.action_hash, None
        )
    except ApprovalConflict as conflict:
        return str(conflict)
    return "Approved. NOC runs the fix now." if decision == "approved" else "Rejected."
