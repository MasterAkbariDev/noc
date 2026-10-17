import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.session import SessionFactory, transaction
from noc.domain.incident_status import IncidentStatus, InvalidTransition
from noc.llm.keys import KeyRefused
from noc.notify.screens import (
    ApprovalRow,
    IncidentRow,
    decide,
    load_approval,
    load_approvals,
    load_incident,
    load_incidents,
    load_keys,
    load_overview,
    load_servers,
    main_menu,
    pending_action_of,
    render_approval,
    render_approvals,
    render_close_confirm,
    render_confirm,
    render_help,
    render_incident,
    render_incidents,
    render_models,
    render_overview,
    render_servers,
)
from noc.notify.settings import (
    MAX_ADMINS,
    BotAdmin,
    NotifyEvents,
    TelegramSettings,
    admin_for_handle,
    find_admin,
    find_by_handle,
    load_offset,
    load_settings,
    read_proxy,
    read_token,
    store_offset,
    store_settings,
)
from noc.notify.telegram import (
    Button,
    CallbackQuery,
    Keyboard,
    TelegramError,
    TelegramMessage,
    TelegramSender,
    TelegramUpdate,
    TelegramUser,
)
from noc.secret_store import SecretStore
from noc.store.incidents import IncidentResolution, close_incident

logger = structlog.get_logger(__name__)

PRIVATE_CHAT: Final = "private"
TEST_TEXT: Final = "[NOC] Test message: NOC notifications reach you here."
EVENT_LABELS: Final = {
    "approval": "Approval needed or expired",
    "escalated": "Escalated to a person",
    "resolved": "Resolved",
    "opened": "Every new incident",
}
SCREEN_PREFIXES: Final = ("m:", "i:", "a:", "y:", "do:")
HELP_TEXT: Final = "\n".join(
    [
        "NOC bot commands:",
        "/menu - the button menu: overview, incidents, approvals, servers, models",
        "/settings - turn messages and event types on or off",
        "/status - what is sent and to whom",
        "/admins - list the admins",
        "/add <user id or @username> - add an admin",
        "/remove <user id or @username> - remove an admin",
        "/mute, /unmute - stop or restart messages to you only",
        "/pause, /resume - stop or restart messages to everyone",
        "/test - send yourself a test message",
    ]
)


@dataclass(frozen=True)
class Send:
    chat_id: str
    text: str
    keyboard: Keyboard | None = None


@dataclass(frozen=True)
class Edit:
    chat_id: str
    message_id: int
    text: str
    keyboard: Keyboard | None = None


@dataclass(frozen=True)
class Answer:
    callback_id: str
    text: str


Reply = Send | Edit | Answer


@dataclass
class Outcome:
    replies: list[Reply] = field(default_factory=list)
    settings: TelegramSettings | None = None
    action: str = ""
    actor: str = ""


class BotApi(Protocol):
    async def send(self, chat_id: str, text: str, keyboard: Keyboard | None = None) -> None: ...

    async def edit(
        self, chat_id: str, message_id: int, text: str, keyboard: Keyboard | None = None
    ) -> None: ...

    async def answer(self, callback_id: str, text: str) -> None: ...

    async def updates(self, offset: int | None) -> list[TelegramUpdate]: ...


BotApiFactory = Callable[[str, str | None], BotApi]


def actor_of(user: TelegramUser) -> str:
    return f"telegram:{user.id}"


def describe_admin(admin: BotAdmin) -> str:
    name = admin.handle
    if admin.user_id is not None and admin.username and not admin.handle.startswith("@"):
        name = f"{admin.handle} (@{admin.username})"
    if admin.ready_since is None:
        return f"- {name}: has not written to the bot yet, so gets no messages"
    return f"- {name}: {'muted' if admin.muted else 'gets messages'}"


def admins_text(settings: TelegramSettings) -> str:
    if not settings.admins:
        return "No admins."
    return "\n".join(["Admins:", *(describe_admin(admin) for admin in settings.admins)])


def status_text(settings: TelegramSettings, admin: BotAdmin) -> str:
    chosen = [label for key, label in EVENT_LABELS.items() if getattr(settings.events, key)]
    linked = sum(1 for item in settings.admins if item.ready_since is not None)
    return "\n".join(
        [
            "NOC notifications",
            f"Messages: {'paused for everyone' if settings.paused else 'on'}",
            f"Sent when: {', '.join(chosen) if chosen else 'nothing is chosen'}",
            f"You: {'muted' if admin.muted else 'getting messages'}",
            f"Admins: {len(settings.admins)} ({linked} have written to the bot)",
        ]
    )


def settings_keyboard(settings: TelegramSettings, admin: BotAdmin) -> Keyboard:
    pause = "Resume messages" if settings.paused else "Pause messages for everyone"
    rows: Keyboard = [[Button(text=pause, callback_data="pause")]]
    for key, label in EVENT_LABELS.items():
        mark = "[x]" if getattr(settings.events, key) else "[ ]"
        rows.append([Button(text=f"{mark} {label}", callback_data=f"ev:{key}")])
    mute = "Unmute me" if admin.muted else "Mute me"
    rows.append([Button(text=mute, callback_data="mute")])
    rows.append([Button(text="⬅️ Menu", callback_data="m:home")])
    return rows


def replace_admin(settings: TelegramSettings, old: BotAdmin, new: BotAdmin) -> TelegramSettings:
    admins = [new if item is old else item for item in settings.admins]
    return settings.model_copy(update={"admins": admins})


def link_admin(
    settings: TelegramSettings, admin: BotAdmin, user: TelegramUser, now: datetime
) -> TelegramSettings:
    username = user.username.lower() if user.username else None
    if admin.user_id == user.id and admin.username == username and admin.ready_since:
        return settings
    linked = admin.model_copy(
        update={"user_id": user.id, "username": username, "ready_since": admin.ready_since or now}
    )
    return replace_admin(settings, admin, linked)


def toggled_event(events: NotifyEvents, key: str) -> NotifyEvents:
    return events.model_copy(update={key: not getattr(events, key)})


def set_paused(settings: TelegramSettings, paused: bool, now: datetime) -> TelegramSettings:
    changes: dict[str, object] = {"paused": paused}
    if not paused and settings.paused:
        changes["active_since"] = now
    return settings.model_copy(update=changes)


def set_muted(settings: TelegramSettings, admin: BotAdmin, muted: bool) -> TelegramSettings:
    return replace_admin(settings, admin, admin.model_copy(update={"muted": muted}))


def add_admin(settings: TelegramSettings, handle: str, actor: str) -> tuple[TelegramSettings, str]:
    fresh = admin_for_handle(handle, actor)
    if find_by_handle(settings, fresh.handle) is not None:
        return settings, f"{fresh.handle} is already an admin."
    if len(settings.admins) >= MAX_ADMINS:
        return settings, f"There are already {MAX_ADMINS} admins."
    updated = settings.model_copy(update={"admins": [*settings.admins, fresh]})
    return updated, f"Added {fresh.handle}. They must open the bot and send /start once."


def remove_admin(settings: TelegramSettings, handle: str) -> tuple[TelegramSettings, str]:
    target = find_by_handle(settings, handle)
    if target is None:
        return settings, f"{handle} is not an admin. /admins lists them."
    if len(settings.admins) == 1:
        return settings, "This is the last admin; add another one before removing it."
    remaining = [item for item in settings.admins if item is not target]
    return settings.model_copy(update={"admins": remaining}), f"Removed {target.handle}."


def command_of(text: str) -> tuple[str, str]:
    head, _, rest = text.strip().partition(" ")
    return head.split("@", 1)[0].lower(), rest.strip()


def handle_command(
    settings: TelegramSettings,
    admin: BotAdmin,
    message: TelegramMessage,
    user: TelegramUser,
    now: datetime,
) -> Outcome:
    chat = str(message.chat.id)
    command, argument = command_of(message.text)
    actor = actor_of(user)
    if command in ("/start", "/menu"):
        text, keyboard = main_menu(settings.panel_url)
        return Outcome([Send(chat, text, keyboard)])
    if command == "/help":
        return Outcome([Send(chat, HELP_TEXT)])
    if command == "/status":
        return Outcome([Send(chat, status_text(settings, admin))])
    if command == "/settings":
        return Outcome(
            [Send(chat, status_text(settings, admin), settings_keyboard(settings, admin))]
        )
    if command == "/admins":
        return Outcome([Send(chat, admins_text(settings))])
    if command == "/test":
        return Outcome([Send(chat, TEST_TEXT)])
    if command in ("/mute", "/unmute"):
        muted = command == "/mute"
        updated = set_muted(settings, admin, muted)
        text = "You will get no NOC messages." if muted else "Messages are back on."
        action = "telegram_admin_muted" if muted else "telegram_admin_unmuted"
        return Outcome([Send(chat, text)], updated, action, actor)
    if command in ("/pause", "/resume"):
        return pause_outcome(settings, chat, command == "/pause", actor, now)
    if command in ("/add", "/remove"):
        return admin_change(settings, chat, command, argument, actor)
    return Outcome([Send(chat, "Unknown command. /help lists the commands.")])


def pause_outcome(
    settings: TelegramSettings, chat: str, paused: bool, actor: str, now: datetime
) -> Outcome:
    updated = set_paused(settings, paused, now)
    text = "Messages are paused for everyone." if paused else "Messages are on again."
    action = "telegram_paused" if paused else "telegram_resumed"
    return Outcome([Send(chat, text)], updated, action, actor)


def admin_change(
    settings: TelegramSettings, chat: str, command: str, argument: str, actor: str
) -> Outcome:
    if not argument:
        return Outcome([Send(chat, f"Usage: {command} <user id or @username>")])
    try:
        if command == "/add":
            updated, text = add_admin(settings, argument, actor)
        else:
            updated, text = remove_admin(settings, argument)
    except KeyRefused as refusal:
        return Outcome([Send(chat, str(refusal))])
    if updated is settings:
        return Outcome([Send(chat, text)])
    action = "telegram_admin_added" if command == "/add" else "telegram_admin_removed"
    return Outcome([Send(chat, text)], updated, action, actor)


def handle_callback(
    settings: TelegramSettings, admin: BotAdmin, query: CallbackQuery, now: datetime
) -> Outcome:
    actor = actor_of(query.sender)
    if query.data == "pause":
        updated = set_paused(settings, not settings.paused, now)
        action = "telegram_paused" if updated.paused else "telegram_resumed"
    elif query.data == "mute":
        updated = set_muted(settings, admin, not admin.muted)
        action = "telegram_admin_muted" if not admin.muted else "telegram_admin_unmuted"
    elif query.data.startswith("ev:") and query.data[3:] in EVENT_LABELS:
        events = toggled_event(settings.events, query.data[3:])
        updated = settings.model_copy(update={"events": events})
        action = "telegram_events_changed"
    else:
        return Outcome([Answer(query.id, "Unknown button")])
    fresh_admin = find_admin(updated, query.sender) or admin
    replies: list[Reply] = [Answer(query.id, "Saved")]
    if query.message is not None:
        replies.append(
            Edit(
                str(query.message.chat.id),
                query.message.message_id,
                status_text(updated, fresh_admin),
                settings_keyboard(updated, fresh_admin),
            )
        )
    return Outcome(replies, updated, action, actor)


def stranger_reply(chat: str, user: TelegramUser) -> Send:
    return Send(
        chat,
        f"You are not an admin of this NOC bot. Your Telegram user id is {user.id}; "
        f"an admin can add you with /add {user.id}.",
    )


def handle_update(settings: TelegramSettings, update: TelegramUpdate, now: datetime) -> Outcome:
    query = update.callback_query
    if query is not None:
        admin = find_admin(settings, query.sender)
        if admin is None:
            return Outcome([Answer(query.id, "Only NOC admins can change this")])
        return handle_callback(settings, admin, query, now)
    message = update.message
    if message is None or message.sender is None or message.chat.type != PRIVATE_CHAT:
        return Outcome()
    user = message.sender
    admin = find_admin(settings, user)
    if admin is None:
        return Outcome([stranger_reply(str(message.chat.id), user)])
    linked = link_admin(settings, admin, user, now)
    current_admin = find_admin(linked, user) or admin
    outcome = handle_command(linked, current_admin, message, user, now)
    if outcome.settings is None and linked is not settings:
        return Outcome(outcome.replies, linked, "telegram_admin_linked", actor_of(user))
    return outcome


def default_api(token: str, proxy: str | None) -> BotApi:
    return TelegramSender(token, proxy)


async def deliver_replies(api: BotApi, replies: list[Reply]) -> None:
    for reply in replies:
        try:
            match reply:
                case Send():
                    await api.send(reply.chat_id, reply.text, reply.keyboard)
                case Edit():
                    await api.edit(reply.chat_id, reply.message_id, reply.text, reply.keyboard)
                case Answer():
                    await api.answer(reply.callback_id, reply.text)
        except TelegramError as failure:
            logger.warning("telegram_reply_failed", error=str(failure))


def is_screen_update(update: TelegramUpdate) -> bool:
    query = update.callback_query
    return query is not None and query.data.startswith(SCREEN_PREFIXES)


def edited(query: CallbackQuery, text: str, keyboard: Keyboard) -> list[Reply]:
    if query.message is None:
        return []
    return [Edit(str(query.message.chat.id), query.message.message_id, text, keyboard)]


def uuid_or_none(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def show_screen(
    session: AsyncSession, settings: TelegramSettings, admin: BotAdmin, data: str
) -> tuple[str, Keyboard, str] | None:
    panel = settings.panel_url
    if data == "m:home":
        return (*main_menu(panel), "")
    if data == "m:overview":
        return (*render_overview(await load_overview(session), panel), "")
    if data == "m:incidents":
        return (*render_incidents(await load_incidents(session), panel), "")
    if data == "m:approvals":
        return (*render_approvals(await load_approvals(session)), "")
    if data == "m:servers":
        return (*render_servers(await load_servers(session)), "")
    if data == "m:models":
        return (*render_models(await load_keys(session)), "")
    if data == "m:settings":
        return (status_text(settings, admin), settings_keyboard(settings, admin), "")
    if data == "m:help":
        return (*render_help(), "")
    return None


async def screen_outcome(
    session: AsyncSession, settings: TelegramSettings, admin: BotAdmin, query: CallbackQuery
) -> Outcome:
    actor = actor_of(query.sender)
    data = query.data
    shown = await show_screen(session, settings, admin, data)
    if shown is not None:
        text, keyboard, note = shown
        return Outcome([Answer(query.id, note), *edited(query, text, keyboard)])
    kind, _, raw = data.partition(":")
    if kind == "do":
        decision, _, raw = raw.partition(":")
        action_id = uuid_or_none(raw)
        if action_id is None:
            return Outcome([Answer(query.id, "Unknown button")])
        if decision == "cl":
            # For close, the id after "do:cl:" is the incident id.
            note = await close_from_bot(session, action_id, actor)
            row = await load_incident(session, action_id)
            if row is None:
                text, keyboard = render_incidents_menu(await load_incidents(session))
            else:
                text, keyboard = render_incident(
                    row, await pending_action_of(session, action_id), settings.panel_url
                )
            return Outcome([Answer(query.id, note), *edited(query, text, keyboard)])
        note = await decide(
            session, action_id, "approved" if decision == "ok" else "rejected", actor
        )
        text, keyboard = render_approvals(await load_approvals(session))
        return Outcome([Answer(query.id, note), *edited(query, text, keyboard)])
    identifier = uuid_or_none(raw)
    if identifier is None:
        return Outcome([Answer(query.id, "Unknown button")])
    if kind == "cl":
        row = await load_incident(session, identifier)
        if row is None or row.status != IncidentStatus.ESCALATED.value:
            return Outcome([Answer(query.id, "Only escalated incidents can be closed.")])
        text, keyboard = render_close_confirm(row)
        return Outcome([Answer(query.id, ""), *edited(query, text, keyboard)])
    if kind == "i":
        row = await load_incident(session, identifier)
        if row is None:
            return Outcome([Answer(query.id, "That incident is gone.")])
        pending = await pending_action_of(session, identifier)
        text, keyboard = render_incident(row, pending, settings.panel_url)
        return Outcome([Answer(query.id, ""), *edited(query, text, keyboard)])
    if kind in ("a", "y"):
        found: ApprovalRow | None = await load_approval(session, identifier)
        if found is None:
            text, keyboard = render_approvals(await load_approvals(session))
            return Outcome(
                [Answer(query.id, "That fix is no longer waiting."), *edited(query, text, keyboard)]
            )
        if kind == "y":
            text, keyboard = render_confirm(found)
        else:
            text, keyboard = render_approval(found, settings.panel_url)
        return Outcome([Answer(query.id, ""), *edited(query, text, keyboard)])
    return Outcome([Answer(query.id, "Unknown button")])


async def close_from_bot(session: AsyncSession, incident_id: uuid.UUID, actor: str) -> str:
    try:
        await close_incident(
            session,
            incident_id,
            IncidentResolution(resolution_note=f"Closed from Telegram by {actor}."),
            actor,
        )
    except LookupError:
        return "That incident is gone."
    except InvalidTransition:
        return "Only escalated incidents can be closed."
    return "Closed."


def render_incidents_menu(rows: list[IncidentRow]) -> tuple[str, Keyboard]:
    return render_incidents(rows, "")


async def handle_screen_update(
    session: AsyncSession, settings: TelegramSettings, update: TelegramUpdate
) -> Outcome:
    query = update.callback_query
    if query is None:
        return Outcome()
    admin = find_admin(settings, query.sender)
    if admin is None:
        return Outcome([Answer(query.id, "Only NOC admins can change this")])
    return await screen_outcome(session, settings, admin, query)


async def poll_once(
    sessions: SessionFactory,
    store: SecretStore,
    make_api: BotApiFactory = default_api,
    clock: Callable[[], datetime] = utc_now,
) -> bool:
    token = await read_token(store)
    if not token:
        return False
    api = make_api(token, await read_proxy(store))
    async with sessions() as session:
        offset = await load_offset(session)
    for update in await api.updates(offset):
        async with transaction(sessions) as session:
            settings = await load_settings(session)
            if is_screen_update(update):
                outcome = await handle_screen_update(session, settings, update)
            else:
                outcome = handle_update(settings, update, clock())
            if outcome.settings is not None:
                await store_settings(session, outcome.settings, outcome.actor, outcome.action)
            await store_offset(session, update.update_id + 1)
        await deliver_replies(api, outcome.replies)
    return True
