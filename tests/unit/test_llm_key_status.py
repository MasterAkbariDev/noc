from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy.exc import OperationalError

from noc.db.session import SessionFactory
from noc.llm.key_status import NullKeyStatus, PostgresKeyStatus


def database_down() -> None:
    raise OperationalError("INSERT", {}, ConnectionError("database is down"))


def broken_sessions() -> SessionFactory:
    return cast(SessionFactory, database_down)


async def test_null_sink_accepts_every_report() -> None:
    sink = NullKeyStatus()
    await sink.record_success("gemini#1a2b3c4d", "gemini")
    await sink.record_failure(
        "gemini#1a2b3c4d", "gemini", "cooling", datetime.now(UTC), "ProviderRateLimited"
    )


async def test_success_report_survives_a_database_outage() -> None:
    sink = PostgresKeyStatus(broken_sessions())
    await sink.record_success("gemini#1a2b3c4d", "gemini")


async def test_failure_report_survives_a_database_outage() -> None:
    sink = PostgresKeyStatus(broken_sessions())
    await sink.record_failure(
        "gemini#1a2b3c4d",
        "gemini",
        "rejected",
        datetime.now(UTC) + timedelta(hours=1),
        "ProviderKeyRejected",
    )
