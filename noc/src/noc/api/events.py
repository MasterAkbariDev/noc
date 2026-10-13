import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from psycopg import sql
from pydantic import BaseModel

from noc.api.deps import get_settings_dep, require_token
from noc.config import Settings
from noc.db.models import IncidentEvent
from noc.db.session import SessionFactory
from noc.store.incidents import EVENTS_CHANNEL

PING_SECONDS = 15.0
PING_FRAME = ": ping\n\n"
CONNECTED_FRAME = ": connected\n\n"

router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(require_token)])


class IncidentEventMessage(BaseModel):
    incident_id: uuid.UUID
    id: int
    ts: datetime
    type: str
    actor: str
    payload: dict[str, Any]


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


async def event_frames(settings: Settings, sessions: SessionFactory) -> AsyncIterator[str]:
    connection = await psycopg.AsyncConnection.connect(settings.libpq_url, autocommit=True)
    try:
        await connection.execute(sql.SQL("LISTEN {}").format(sql.Identifier(EVENTS_CHANNEL)))
        yield CONNECTED_FRAME
        while True:
            async for notification in connection.notifies(timeout=PING_SECONDS):
                frame = await load_event_frame(sessions, notification.payload)
                if frame is not None:
                    yield frame
            yield PING_FRAME
    finally:
        await connection.close()


@router.get("/stream")
async def stream_events(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    request: Request,
) -> StreamingResponse:
    return StreamingResponse(
        event_frames(settings, request.app.state.sessions),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
