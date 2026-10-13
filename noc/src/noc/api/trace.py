import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_token
from noc.api.schemas import AgentRunView, IncidentTrace, LlmCallView, ToolCallView
from noc.db.models import AgentRun, Incident, LlmCall, ToolCall

router = APIRouter(prefix="/api/incidents", tags=["trace"], dependencies=[Depends(require_token)])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/{incident_id}/trace")
async def get_incident_trace(incident_id: uuid.UUID, session: Session) -> IncidentTrace:
    if await session.get(Incident, incident_id) is None:
        raise HTTPException(404, "incident not found")
    runs = await session.scalars(
        select(AgentRun)
        .where(AgentRun.incident_id == incident_id)
        .order_by(AgentRun.started_at, AgentRun.id)
    )
    tools = await session.scalars(
        select(ToolCall)
        .where(ToolCall.incident_id == incident_id)
        .order_by(ToolCall.started_at, ToolCall.id)
    )
    llm_calls = await session.scalars(
        select(LlmCall)
        .where(LlmCall.incident_id == incident_id)
        .order_by(LlmCall.created_at, LlmCall.id)
    )
    return IncidentTrace(
        agent_runs=[AgentRunView.model_validate(row) for row in runs],
        tool_calls=[ToolCallView.model_validate(row) for row in tools],
        llm_calls=[LlmCallView.model_validate(row) for row in llm_calls],
    )
