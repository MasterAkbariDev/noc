import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from psycopg import sql
from pydantic import BaseModel

from noc.api.deps import Principal, get_settings_dep, require_role, require_token
from noc.api.tickets import TICKET_TTL_SECONDS, TicketGrant, TicketStore
from noc.auth.roles import Role
from noc.auth.sessions import is_session_live
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import IncidentEvent
from noc.db.session import SessionFactory
from noc.store.incidents import EVENTS_CHANNEL

PING_SECONDS = 15.0
PING_FRAME = ": ping\n\n"
CONNECTED_FRAME = ": connected\n\n"

router = APIRouter(prefix="/api/events", tags=["events"])


class IncidentEventMessage(BaseModel):
    incident_id: uuid.UUID
    id: int
    ts: datetime
    type: str
    actor: str
    payload: dict[str, Any]


class StreamTicket(BaseModel):
    ticket: str
    expires_in: int


def require_stream_access(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
    ticket: Annotated[str | None, Query()] = None,
) -> TicketGrant:
    tickets: TicketStore = request.app.state.tickets
    if ticket is not None:
        grant = tickets.consume(ticket)
        if grant is not None:
            return grant
    require_token(settings, authorization)
    return TicketGrant(session_hash=None)


StillAllowed = Callable[[], Awaitable[bool]]


def session_check(sessions: SessionFactory, settings: Settings, grant: TicketGrant) -> StillAllowed:
    async def still_allowed() -> bool:
        if grant.session_hash is None:
            return True
        async with sessions() as session:
            return await is_session_live(session, grant.session_hash, settings, utc_now())

    return still_allowed


def parse_notification(payload: str) -> tuple[uuid.UUID, int] | None:
    incident_text, separator, event_text = payload.partition(":")
    if not separator or not event_text.isdigit():
        return None
    try:
        return uuid.UUID(incident_text), int(event_text)
    except ValueError:
        return None


def event_frame(message: IncidentEventMessage) -> str:
    return f"event: incident_event\ndata: {message.model_dump_json()}\n\n"


async def load_event_frame(sessions: SessionFactory, payload: str) -> str | None:
    parsed = parse_notification(payload)
    if parsed is None:
        return None
    incident_id, event_id = parsed
    async with sessions() as session:
        event = await session.get(IncidentEvent, event_id)
    if event is None or event.incident_id != incident_id:
        return None
    return event_frame(
        IncidentEventMessage(
            incident_id=event.incident_id,
            id=event.id,
            ts=event.ts,
            type=event.type,
            actor=event.actor,
            payload=event.payload,
        )
    )


async def event_frames(
    settings: Settings, sessions: SessionFactory, still_allowed: StillAllowed
) -> AsyncIterator[str]:
    connection = await psycopg.AsyncConnection.connect(settings.libpq_url, autocommit=True)
    try:
        await connection.execute(sql.SQL("LISTEN {}").format(sql.Identifier(EVENTS_CHANNEL)))
        yield CONNECTED_FRAME
        while True:
            async for notification in connection.notifies(timeout=PING_SECONDS):
                frame = await load_event_frame(sessions, notification.payload)
                if frame is not None:
                    yield frame
            if not await still_allowed():
                return
            yield PING_FRAME
    finally:
        await connection.close()


@router.post("/ticket")
async def issue_stream_ticket(
    request: Request, principal: Annotated[Principal, Depends(require_role(Role.VIEWER))]
) -> StreamTicket:
    tickets: TicketStore = request.app.state.tickets
    return StreamTicket(ticket=tickets.issue(principal.session_hash), expires_in=TICKET_TTL_SECONDS)


@router.get("/stream")
async def stream_events(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    request: Request,
    grant: Annotated[TicketGrant, Depends(require_stream_access)],
) -> StreamingResponse:
    sessions: SessionFactory = request.app.state.sessions
    return StreamingResponse(
        event_frames(settings, sessions, session_check(sessions, settings, grant)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
