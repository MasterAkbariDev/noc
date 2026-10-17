import uuid
from datetime import UTC, datetime

from noc.notify.screens import (
    ApprovalRow,
    IncidentRow,
    Overview,
    TargetRow,
    main_menu,
    render_approval,
    render_confirm,
    render_incidents,
    render_overview,
    render_servers,
)
from noc.notify.telegram import Button, keyboard_markup

NOW = datetime(2026, 10, 17, 14, 0, tzinfo=UTC)
PANEL = "https://stage.example.com"


def callbacks(keyboard: list[list[Button]]) -> list[str]:
    return [button.callback_data for row in keyboard for button in row]


def test_main_menu_offers_every_section_and_the_panel_link() -> None:
    text, keyboard = main_menu(PANEL)
    assert "NOC control" in text
    assert callbacks(keyboard)[:7] == [
        "m:overview",
        "m:incidents",
        "m:approvals",
        "m:servers",
        "m:models",
        "m:settings",
        "m:help",
    ]
    assert keyboard[-1][0].url == PANEL


def test_main_menu_without_a_panel_url_has_no_link_button() -> None:
    _, keyboard = main_menu("")
    assert all(button.url is None for row in keyboard for button in row)


def test_overview_counts_are_shown_with_a_way_back() -> None:
    text, keyboard = render_overview(
        Overview(active=2, escalated=1, pending=3, targets=2, halted=0, keys_ok=4, keys_total=5),
        PANEL,
    )
    assert "Waiting for your approval: 3" in text
    assert "Model keys working: 4 of 5" in text
    assert callbacks(keyboard)[-1] == "m:home"


def test_incident_buttons_open_the_incident_and_show_its_status_icon() -> None:
    incident = IncidentRow(
        id=uuid.uuid4(),
        title="DiskAlmostFull on demo-1",
        status="RESOLVED",
        reason=None,
        root_cause="disk_full_logs",
        confidence=0.95,
        target="demo-1",
        opened_at=NOW,
    )
    text, keyboard = render_incidents([incident], PANEL)
    assert "✅ DiskAlmostFull on demo-1" in text
    assert callbacks(keyboard)[0] == f"i:{incident.id}"


def test_approval_card_has_approve_and_reject_and_confirm_step() -> None:
    row = ApprovalRow(
        action_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        incident_title="HostCPUSaturated on demo-1",
        action_type="throttle_cpu",
        resource_id="job:report-gen",
        target="demo-1",
        environment="lab",
        impact=5,
        reasons=["not_on_auto_list"],
    )
    text, keyboard = render_approval(row, PANEL)
    assert "throttle_cpu on job:report-gen" in text
    assert f"y:{row.action_id}" in callbacks(keyboard)
    assert f"do:no:{row.action_id}" in callbacks(keyboard)

    confirm_text, confirm_keyboard = render_confirm(row)
    assert "runs right away" in confirm_text
    assert f"do:ok:{row.action_id}" in callbacks(confirm_keyboard)
    assert f"a:{row.action_id}" in callbacks(confirm_keyboard)


def test_callback_data_stays_under_telegram_limit() -> None:
    row_id = uuid.uuid4()
    for data in (f"do:ok:{row_id}", f"y:{row_id}", f"i:{row_id}", f"a:{row_id}"):
        assert len(data.encode()) <= 64


def test_servers_show_halted_and_busy_state() -> None:
    text, _ = render_servers(
        [
            TargetRow("demo-1", "lab", "approval_required", False, "DiskAlmostFull on demo-1"),
            TargetRow("prod-1", "prod", "observe_only", True, None),
        ]
    )
    assert "demo-1 (lab): 🟡 needs approval" in text
    assert "🔎 DiskAlmostFull on demo-1" in text
    assert "prod-1 (prod): ⛔ halted" in text


def test_url_buttons_are_sent_without_callback_data() -> None:
    markup = keyboard_markup(
        [[Button(text="Open", url=PANEL)], [Button(text="Go", callback_data="m:home")]]
    )
    assert markup["inline_keyboard"][0] == [{"text": "Open", "url": PANEL}]
    assert markup["inline_keyboard"][1] == [{"text": "Go", "callback_data": "m:home"}]
