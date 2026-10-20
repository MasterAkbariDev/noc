import uuid

from noc.api.schemas import (
    IncidentStory,
    StoryAction,
    StoryAdvice,
    StoryDid,
    StoryFound,
    StoryPoint,
    StoryText,
)
from noc.notify.cards import IncidentCard, RunLine, card_keyboard, card_text
from noc.notify.telegram import MESSAGE_MAX_LENGTH, keyboard_markup
from noc.reporting.operator_guide import GuideStep

INCIDENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
ACTION_ID = uuid.UUID("99999999-2222-3333-4444-555555555555")


def story(status: str = "ESCALATED", **changes: object) -> IncidentStory:
    values: dict[str, object] = {
        "id": INCIDENT_ID,
        "title": "ServiceDown on demo-1/svc:demo-shop",
        "target": "demo-1",
        "severity": "critical",
        "status": status,
        "status_label": "Needs you",
        "headline": "",
        "steps": [],
        "what_happened": StoryText(text="demo-shop stopped at 10:00 UTC.", technical=None),
        "what_we_found": StoryFound(
            text="Root cause: the service crashed (85% confidence).",
            root_cause_code="service_crashed",
            root_cause_label="Service crashed",
            confidence=0.85,
            points=[
                StoryPoint(
                    text="demo-shop exited with <code 137>",
                    agent="logs",
                    label="F-1",
                    evidence=[],
                    grounded=True,
                )
            ],
        ),
        "what_we_did": StoryDid(
            text="Nothing was run yet.",
            considered=[
                StoryAction(
                    action="start_service",
                    action_label="Start the service on demo-1",
                    verdict="approval",
                    verdict_label="Waiting for approval",
                    reasons=[],
                    technical=[],
                )
            ],
        ),
        "what_you_should_do": StoryAdvice(
            text="Start it again by hand.",
            steps=[GuideStep(text="Start it.", command="sudo systemctl start demo-shop.service")],
        ),
    }
    values.update(changes)
    return IncidentStory.model_validate(values)


def card(
    status: str = "ESCALATED", pending: uuid.UUID | None = None, **changes: object
) -> IncidentCard:
    runs = [
        RunLine(agent="logs", status="succeeded", tool_calls=3, llm_calls=2, seconds=4.2),
        RunLine(agent="diagnosis", status="succeeded", tool_calls=0, llm_calls=1, seconds=12.0),
    ]
    return IncidentCard(story(status, **changes), "lab", runs, pending)


def test_card_has_every_section_in_plain_words() -> None:
    text = card_text(card(), "Escalated to a person")
    assert text.startswith(
        "🚨 <b>Escalated to a person</b>\n<b>ServiceDown on demo-1/svc:demo-shop</b>"
    )
    for heading in ("What happened", "What the agents did", "Result", "What you should do"):
        assert f"<b>{heading}</b>" in text
    assert "✅ <b>Logs specialist</b> · 3 checks · 2 AI calls · 4.2 s" in text
    assert "✅ <b>Diagnosis agent</b> · 0 checks · 1 AI call · 12 s" in text
    assert "⏳ Start the service on demo-1 — Waiting for approval" in text
    assert "<code>sudo systemctl start demo-shop.service</code>" in text


def test_text_from_the_server_is_escaped() -> None:
    text = card_text(card(), "")
    assert "exited with &lt;code 137&gt;" in text
    assert "<code 137>" not in text


def test_a_new_incident_says_the_agents_are_working() -> None:
    fresh = IncidentCard(
        story(
            "INVESTIGATING",
            what_we_found=StoryFound(
                text="", root_cause_code=None, root_cause_label=None, confidence=None, points=[]
            ),
            what_we_did=StoryDid(text="Nothing yet.", considered=[]),
            what_you_should_do=StoryAdvice(text="Nothing to do yet.", steps=[]),
        ),
        "lab",
        [],
    )
    text = card_text(fresh, "New incident")
    assert "The agents are looking at the server now." in text
    assert "Result" not in text
    assert "What you should do" not in text


def test_long_stories_are_shortened_to_fit_one_message() -> None:
    long = "x" * 2000
    steps = [GuideStep(text=long, command=long) for _ in range(6)]
    text = card_text(card(what_you_should_do=StoryAdvice(text=long, steps=steps)), "Escalated")
    assert len(text) <= MESSAGE_MAX_LENGTH
    assert "…" in text


def test_the_panel_link_is_a_button_and_a_waiting_fix_can_be_reviewed() -> None:
    keyboard = card_keyboard(card(pending=ACTION_ID), "https://noc.example/")
    markup = keyboard_markup(keyboard)
    assert markup["inline_keyboard"] == [
        [{"text": "✅ Review the fix", "callback_data": f"a:{ACTION_ID}"}],
        [{"text": "🌐 Open in panel", "url": f"https://noc.example/incidents/{INCIDENT_ID}"}],
    ]
    assert "https://" not in card_text(card(), "")


def test_without_a_panel_url_there_is_no_link_button() -> None:
    assert card_keyboard(card(), "") == []
