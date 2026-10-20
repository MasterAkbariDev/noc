import uuid
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.schemas import IncidentStory
from noc.api.story import load_story
from noc.db.models import AgentRun, Incident, Target
from noc.notify.telegram import MESSAGE_MAX_LENGTH, Button, Keyboard

SEVERITY_ICON: Final[dict[str, str]] = {"critical": "🔴", "warning": "🟠", "info": "🔵"}
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
AGENT_NAMES: Final[dict[str, str]] = {
    "supervisor": "Supervisor",
    "metrics": "Metrics specialist",
    "logs": "Logs specialist",
    "network": "Network specialist",
    "security": "Security specialist",
    "investigator": "Investigator",
    "diagnosis": "Diagnosis agent",
}
RUN_ICON: Final[dict[str, str]] = {"succeeded": "✅", "failed": "❌", "running": "⏳"}
VERDICT_ICON: Final[dict[str, str]] = {
    "ran": "✅",
    "failed": "❌",
    "running": "⏳",
    "approval": "⏳",
    "waiting": "⏸",
    "rejected": "⛔",
    "expired": "⌛",
    "cancelled": "✖️",
    "unknown": "❔",
    "blocked": "🚫",
}
CAUSE_PREFIX: Final = "Root cause: "
NEEDS_YOU: Final = frozenset({"ESCALATED", "AWAITING_APPROVAL"})
DONE: Final = frozenset({"RESOLVED", "SELF_RESOLVED", "CLOSED"})


@dataclass(frozen=True)
class Limits:
    text: int
    runs: int
    points: int
    actions: int
    steps: int
    commands: bool


FULL: Final = Limits(text=360, runs=8, points=3, actions=3, steps=4, commands=True)
SHORT: Final = Limits(text=200, runs=5, points=2, actions=2, steps=3, commands=False)
TINY: Final = Limits(text=120, runs=3, points=1, actions=1, steps=2, commands=False)


@dataclass(frozen=True)
class RunLine:
    agent: str
    status: str
    tool_calls: int
    llm_calls: int
    seconds: float | None


@dataclass(frozen=True)
class IncidentCard:
    story: IncidentStory
    environment: str
    runs: list[RunLine]
    pending_action: uuid.UUID | None = None


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def safe(text: str, limit: int) -> str:
    return escape(clip(text, limit), quote=False)


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def agent_name(agent: str) -> str:
    return AGENT_NAMES.get(agent, agent.replace("_", " ").capitalize())


def run_line(run: RunLine) -> str:
    parts = [plural(run.tool_calls, "check"), plural(run.llm_calls, "AI call")]
    if run.seconds is not None:
        parts.append(f"{run.seconds:.0f} s" if run.seconds >= 10 else f"{run.seconds:.1f} s")
    icon = RUN_ICON.get(run.status, "•")
    return f"{icon} <b>{escape(agent_name(run.agent))}</b> · {' · '.join(parts)}"


def header(card: IncidentCard, headline: str) -> list[str]:
    story = card.story
    severity = SEVERITY_ICON.get(story.severity, "⚪")
    icon = STATUS_ICON.get(story.status, "🛰")
    lines = [f"{icon} <b>{escape(headline)}</b>"] if headline else []
    lines.append(f"<b>{safe(story.title, 160)}</b>")
    lines.append(
        f"🖥 <code>{safe(story.target, 60)}</code> · {escape(card.environment)} · "
        f"{severity} {escape(story.severity.capitalize())} · {safe(story.status_label, 40)}"
    )
    return lines


def happened_section(story: IncidentStory, limits: Limits) -> list[str]:
    return ["📍 <b>What happened</b>", safe(story.what_happened.text, limits.text)]


def agents_section(card: IncidentCard, limits: Limits) -> list[str]:
    found = card.story.what_we_found
    if not card.runs and not found.points:
        if card.story.status in DONE or card.story.status in NEEDS_YOU:
            return []
        return ["🤖 <b>What the agents are doing</b>", "The agents are looking at the server now."]
    lines = ["🤖 <b>What the agents did</b>"]
    lines.extend(run_line(run) for run in card.runs[: limits.runs])
    if len(card.runs) > limits.runs:
        lines.append(f"… and {plural(len(card.runs) - limits.runs, 'more run')}")
    cause = found.text.removeprefix(CAUSE_PREFIX)
    lines.append(f"🧩 <b>Root cause:</b> {safe(cause, limits.text)}")
    for point in found.points[: limits.points]:
        mark = "✔️" if point.grounded else "⚠️"
        who = escape(agent_name(point.agent))
        lines.append(f"  {mark} {safe(point.text, limits.text // 2)} — <i>{who}</i>")
    return lines


def result_section(story: IncidentStory, limits: Limits) -> list[str]:
    did = story.what_we_did
    if not did.considered and story.status not in DONE:
        return []
    lines = ["🔧 <b>Result</b>", safe(did.text, limits.text)]
    for action in did.considered[: limits.actions]:
        icon = VERDICT_ICON.get(action.verdict, "•")
        label = safe(action.action_label, 80)
        lines.append(f"  {icon} {label} — {safe(action.verdict_label, 40)}")
    return lines


def advice_section(story: IncidentStory, limits: Limits) -> list[str]:
    advice = story.what_you_should_do
    if story.status not in NEEDS_YOU and not advice.steps:
        return []
    lines = ["👉 <b>What you should do</b>", safe(advice.text, limits.text)]
    for number, step in enumerate(advice.steps[: limits.steps], start=1):
        lines.append(f"{number}. {safe(step.text, limits.text // 2)}")
        if limits.commands and step.command:
            lines.append(f"<code>{safe(step.command, 160)}</code>")
    return lines


def compose(card: IncidentCard, headline: str, limits: Limits) -> str:
    sections = [
        header(card, headline),
        happened_section(card.story, limits),
        agents_section(card, limits),
        result_section(card.story, limits),
        advice_section(card.story, limits),
    ]
    return "\n\n".join("\n".join(section) for section in sections if section)


def card_text(card: IncidentCard, headline: str = "") -> str:
    for limits in (FULL, SHORT, TINY):
        text = compose(card, headline, limits)
        if len(text) <= MESSAGE_MAX_LENGTH:
            return text
    return "\n".join(header(card, headline))


def panel_button(panel_url: str, incident_id: uuid.UUID) -> list[Button]:
    if not panel_url:
        return []
    url = f"{panel_url.rstrip('/')}/incidents/{incident_id}"
    return [Button(text="🌐 Open in panel", url=url)]


def card_keyboard(card: IncidentCard, panel_url: str) -> Keyboard:
    rows: Keyboard = []
    if card.pending_action is not None:
        rows.append([Button(text="✅ Review the fix", callback_data=f"a:{card.pending_action}")])
    button = panel_button(panel_url, card.story.id)
    if button:
        rows.append(button)
    return rows


def run_seconds(started_at: datetime, ended_at: datetime | None) -> float | None:
    return None if ended_at is None else max((ended_at - started_at).total_seconds(), 0.0)


async def load_card(
    session: AsyncSession, incident_id: uuid.UUID, pending_action: uuid.UUID | None = None
) -> IncidentCard | None:
    story = await load_story(session, incident_id)
    if story is None:
        return None
    incident = await session.get_one(Incident, incident_id)
    target = await session.get_one(Target, incident.target_id)
    runs = await session.scalars(
        select(AgentRun)
        .where(AgentRun.incident_id == incident_id)
        .order_by(AgentRun.started_at, AgentRun.id)
    )
    return IncidentCard(
        story=story,
        environment=target.environment,
        runs=[
            RunLine(
                agent=run.agent,
                status=run.status,
                tool_calls=run.tool_calls,
                llm_calls=run.llm_calls,
                seconds=run_seconds(run.started_at, run.ended_at),
            )
            for run in runs
        ],
        pending_action=pending_action,
    )
