from datetime import datetime
from typing import Literal, Protocol

import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from noc.db.base import utc_now
from noc.db.models import LlmKeyStatus
from noc.db.session import SessionFactory, transaction

logger = structlog.get_logger(__name__)

RecordedState = Literal["ok", "cooling", "rejected"]


class KeyStatusSink(Protocol):
    async def record_success(self, label: str, provider: str) -> None: ...

    async def record_failure(
        self,
        label: str,
        provider: str,
        state: RecordedState,
        cooling_until: datetime | None,
        error_name: str,
    ) -> None: ...


class NullKeyStatus:
    async def record_success(self, label: str, provider: str) -> None:
        return None

    async def record_failure(
        self,
        label: str,
        provider: str,
        state: RecordedState,
        cooling_until: datetime | None,
        error_name: str,
    ) -> None:
        return None


class PostgresKeyStatus:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def record_success(self, label: str, provider: str) -> None:
        now = utc_now()
        await self._upsert(
            {
                "label": label,
                "provider": provider,
                "state": "ok",
                "cooling_until": None,
                "last_success_at": now,
                "updated_at": now,
            }
        )

    async def record_failure(
        self,
        label: str,
        provider: str,
        state: RecordedState,
        cooling_until: datetime | None,
        error_name: str,
    ) -> None:
        now = utc_now()
        await self._upsert(
            {
                "label": label,
                "provider": provider,
                "state": state,
                "cooling_until": cooling_until,
                "last_error": error_name,
                "last_error_at": now,
                "updated_at": now,
            }
        )

    async def _upsert(self, values: dict[str, object]) -> None:
        statement = insert(LlmKeyStatus).values(values)
        changed = {column: statement.excluded[column] for column in values if column != "label"}
        try:
            async with transaction(self._sessions) as session:
                await session.execute(
                    statement.on_conflict_do_update(index_elements=["label"], set_=changed)
                )
        except SQLAlchemyError as error:
            logger.warning("llm_key_status_write_failed", error=type(error).__name__)
