from datetime import UTC, datetime, timedelta

import pytest

from noc.llm.keys import KeyRefused
from noc.notify.bot import Answer, Edit, Send, handle_update
from noc.notify.outbox import recipient_channel
from noc.notify.settings import BotAdmin, TelegramSettings, merge_admins, recipients
from noc.notify.telegram import TelegramUpdate

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
ALI = 111111
SARA = 222222
STRANGER = 999999


def message(
    user_id: int, text: str, username: str | None = None, chat_type: str = "private"
) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 5,
                "chat": {"id": user_id, "type": chat_type},
                "from": {"id": user_id, "username": username, "first_name": "x"},
                "text": text,
            },
        }
    )


def button(user_id: int, data: str) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 2,
            "callback_query": {
                "id": "cb-1",
                "from": {"id": user_id, "first_name": "x"},
                "message": {"message_id": 7, "chat": {"id": user_id, "type": "private"}},
                "data": data,
            },
        }
    )


def linked(user_id: int, **changes: object) -> BotAdmin:
    values: dict[str, object] = {
        "handle": str(user_id),
        "user_id": user_id,
        "ready_since": NOW - timedelta(days=1),
    }
    values.update(changes)
    return BotAdmin.model_validate(values)


def two_admins() -> TelegramSettings:
    return TelegramSettings(admins=[linked(ALI), linked(SARA)])


def only_text(replies: list[Send | Edit | Answer]) -> str:
    [reply] = replies
    assert isinstance(reply, Send)
    return reply.text


def test_a_stranger_is_told_their_id_and_changes_nothing() -> None:
    outcome = handle_update(two_admins(), message(STRANGER, "/pause"), NOW)
    assert outcome.settings is None
    assert str(STRANGER) in only_text(outcome.replies)


def test_group_chats_are_ignored() -> None:
    outcome = handle_update(two_admins(), message(ALI, "/pause", chat_type="group"), NOW)
    assert outcome.settings is None
    assert outcome.replies == []


def test_start_links_an_admin_added_by_username() -> None:
    settings = TelegramSettings(admins=[BotAdmin(handle="@ali_ops", username="ali_ops")])
    outcome = handle_update(settings, message(ALI, "/start", username="Ali_Ops"), NOW)
    assert outcome.action == "telegram_admin_linked"
    assert outcome.actor == f"telegram:{ALI}"
    assert outcome.settings is not None
    [admin] = outcome.settings.admins
    assert (admin.user_id, admin.ready_since) == (ALI, NOW)
    [reply] = outcome.replies
    assert isinstance(reply, Send)
    assert reply.keyboard is not None
    assert "m:settings" in [button.callback_data for row in reply.keyboard for button in row]


def test_an_already_linked_admin_is_not_rewritten() -> None:
    outcome = handle_update(two_admins(), message(ALI, "/status"), NOW)
    assert outcome.settings is None
    assert "Messages: on" in only_text(outcome.replies)


def test_commands_addressed_to_the_bot_by_name_work() -> None:
    outcome = handle_update(two_admins(), message(ALI, "/pause@noc_bot"), NOW)
    assert outcome.settings is not None
    assert outcome.settings.paused is True


def test_resume_restarts_the_window_so_paused_events_are_not_replayed() -> None:
    paused = two_admins().model_copy(update={"paused": True})
    outcome = handle_update(paused, message(ALI, "/resume"), NOW)
    assert outcome.settings is not None
    assert outcome.settings.paused is False
    assert outcome.settings.active_since == NOW


def test_mute_only_affects_the_sender() -> None:
    outcome = handle_update(two_admins(), message(ALI, "/mute"), NOW)
    assert outcome.action == "telegram_admin_muted"
    assert outcome.settings is not None
    assert [admin.muted for admin in outcome.settings.admins] == [True, False]
    assert [admin.user_id for admin in recipients(outcome.settings)] == [SARA]


def test_add_takes_an_id_or_a_username() -> None:
    by_id = handle_update(two_admins(), message(ALI, "/add 333333"), NOW)
    by_name = handle_update(two_admins(), message(ALI, "/add @Ops_Lead"), NOW)
    assert by_id.settings is not None
    assert by_name.settings is not None
    assert by_id.settings.admins[-1].user_id == 333333
    assert by_name.settings.admins[-1].username == "ops_lead"
    assert by_id.settings.admins[-1].added_by == f"telegram:{ALI}"
    assert "/start" in only_text(by_id.replies)


@pytest.mark.parametrize("argument", ["", "not a user", "@abc", str(SARA), f"{SARA}"])
def test_add_refuses_bad_or_duplicate_users(argument: str) -> None:
    outcome = handle_update(two_admins(), message(ALI, f"/add {argument}"), NOW)
    assert outcome.settings is None


def test_remove_keeps_at_least_one_admin() -> None:
    removed = handle_update(two_admins(), message(ALI, f"/remove {SARA}"), NOW)
    assert removed.settings is not None
    assert [admin.user_id for admin in removed.settings.admins] == [ALI]
    last = handle_update(removed.settings, message(ALI, f"/remove {ALI}"), NOW)
    assert last.settings is None
    assert "last admin" in only_text(last.replies)


def test_settings_shows_buttons_and_a_button_toggles_an_event() -> None:
    shown = handle_update(two_admins(), message(ALI, "/settings"), NOW)
    [reply] = shown.replies
    assert isinstance(reply, Send)
    assert reply.keyboard is not None
    callbacks = [row[0].callback_data for row in reply.keyboard]
    assert callbacks == [
        "pause",
        "ev:approval",
        "ev:escalated",
        "ev:resolved",
        "ev:opened",
        "mute",
        "m:home",
    ]

    toggled = handle_update(two_admins(), button(ALI, "ev:opened"), NOW)
    assert toggled.settings is not None
    assert toggled.settings.events.opened is True
    assert toggled.action == "telegram_events_changed"
    assert isinstance(toggled.replies[0], Answer)
    assert isinstance(toggled.replies[1], Edit)


def test_buttons_from_strangers_or_with_unknown_data_change_nothing() -> None:
    stranger = handle_update(two_admins(), button(STRANGER, "pause"), NOW)
    unknown = handle_update(two_admins(), button(ALI, "ev:shell"), NOW)
    assert stranger.settings is None
    assert unknown.settings is None


def test_unlinked_and_muted_admins_get_no_messages() -> None:
    settings = TelegramSettings(
        admins=[
            linked(ALI),
            linked(SARA, muted=True),
            BotAdmin(handle="@waiting", username="waiting"),
            BotAdmin(handle="444444", user_id=444444),
        ]
    )
    assert [admin.user_id for admin in recipients(settings)] == [ALI]


def test_merge_keeps_link_state_and_drops_duplicates() -> None:
    current = [linked(ALI, username="ali_ops", muted=True)]
    merged = merge_admins(["@ali_ops", str(ALI), " 555555 ", ""], current, "panel")
    assert [admin.handle for admin in merged] == [str(ALI), "555555"]
    assert merged[0].muted is True


def test_merge_refuses_a_bad_handle() -> None:
    with pytest.raises(KeyRefused):
        merge_admins(["ali ops"], [], "panel")


def test_recipient_channels_fit_the_column_and_differ() -> None:
    largest = recipient_channel(2**53)
    assert len(largest) <= 16
    assert recipient_channel(ALI) != recipient_channel(SARA)
    assert recipient_channel(0) == "tg:0"
