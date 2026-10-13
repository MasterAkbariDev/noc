import uuid

from noc.db.models import LlmCall
from noc.db.session import SessionFactory, transaction
from noc.llm.cassette import request_key
from noc.llm.client import LLMClient, describe_error
from noc.llm.types import LLMRequest, LLMResponse


class RecordingLLM:
    def __init__(self, inner: LLMClient, sessions: SessionFactory) -> None:
        self._inner = inner
        self._sessions = sessions

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            response = await self._inner.complete(request)
        except Exception as exc:
            await self._store(request, None, error=describe_error(exc))
            raise
        await self._store(request, response, error=None)
        return response

    async def _store(
        self, request: LLMRequest, response: LLMResponse | None, error: str | None
    ) -> None:
        incident_id = request.context.incident_id
        row = LlmCall(
            incident_id=uuid.UUID(incident_id) if incident_id else None,
            agent=request.context.agent,
            tier=request.tier,
            provider=response.provider if response else "none",
            model=response.model if response else "none",
            mode=response.mode if response else "error",
            request_hash=request_key(request),
            tokens_in=response.usage.tokens_in if response else 0,
            tokens_out=response.usage.tokens_out if response else 0,
            latency_ms=response.latency_ms if response else 0,
            wait_ms=response.wait_ms if response else 0,
            fallback=response.fallback if response else False,
            finish_reason=response.finish_reason if response else None,
            redactions=response.redactions if response else 0,
            error=error,
        )
        async with transaction(self._sessions) as session:
            session.add(row)
