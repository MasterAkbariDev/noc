from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from noc.db.base import utc_now
from noc.db.models import Endpoint
from noc.db.session import SessionFactory, transaction
from noc.endpoints import service

pytestmark = pytest.mark.integration


async def fake_check(host: str, ssh_port: int, url: str | None) -> dict[str, Any]:
    return {"ssh": {"open": True, "banner": "SSH-2.0-test"}, "checked_at": "now"}


async def test_only_stale_or_unchecked_servers_are_rechecked(
    sessions: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "run_check", fake_check)
    now = utc_now()
    async with transaction(sessions) as session:
        session.add_all(
            [
                Endpoint(
                    name="fresh",
                    host="10.0.0.1",
                    ssh_port=22,
                    created_by="t",
                    last_checked_at=now - timedelta(minutes=1),
                    last_result={"ssh": {"open": False}},
                ),
                Endpoint(
                    name="stale",
                    host="10.0.0.2",
                    ssh_port=22,
                    created_by="t",
                    last_checked_at=now - timedelta(minutes=30),
                    last_result={"ssh": {"open": False}},
                ),
                Endpoint(name="never", host="10.0.0.3", ssh_port=22, created_by="t"),
            ]
        )

    async with transaction(sessions) as session:
        rechecked = await service.recheck_stale(session, utc_now())
    assert rechecked == 2

    async with sessions() as session:
        rows = {row.name: row for row in await session.scalars(select(Endpoint))}
    assert rows["fresh"].last_result == {"ssh": {"open": False}}
    assert rows["stale"].last_result["ssh"]["open"] is True
    assert rows["never"].last_checked_at is not None
