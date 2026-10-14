from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.auth.roles import Role
from noc.auth.users import create_user
from noc.config import Settings
from noc.db.models import Incident, Target
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
BASE_URL = "http://localhost"
PASSWORD = "correct horse battery"
LIST_PATH = "/api/incidents"

SEEDED = [
    ("demo-1", "Disk almost full", "NEW"),
    ("db-1", "Backup late", "RESOLVED"),
    ("web-1", "Service down", "ESCALATED"),
    ("cache-1", "Load 100% spike", "CLOSED"),
    ("cache-2", "Load 1000 spike", "NEW"),
    ("queue-1", "queue_depth high", "NEW"),
]


@pytest.fixture
async def app(sessions: SessionFactory, database_url: str) -> FastAPI:
    settings = Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        session_cookie_secure=False,
        _env_file=None,
    )
    application = create_app(settings)
    application.state.settings = settings
    application.state.sessions = sessions
    return application


@pytest.fixture
async def seeded(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        for name in sorted({target for target, _, _ in SEEDED}):
            await add_target(
                session, name, "10.0.0.2", f"https://{name}:9443", Environment.LAB, KEY_ID
            )
    async with transaction(sessions) as session:
        targets = {target.name: target.id for target in await session.scalars(select(Target))}
        for target, title, status in SEEDED:
            session.add(
                Incident(
                    target_id=targets[target],
                    status=status,
                    severity="warning",
                    title=title,
                    trace_id="a" * 32,
                )
            )


@pytest.fixture
async def client(app, seeded) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as http:
        yield http


def titles(response: httpx.Response) -> set[str]:
    assert response.status_code == 200, response.text
    return {row["title"] for row in response.json()}


async def test_search_matches_the_title_ignoring_case(client: httpx.AsyncClient) -> None:
    response = await client.get(LIST_PATH, params={"q": "DISK"}, headers=bearer())

    assert titles(response) == {"Disk almost full"}


async def test_search_matches_the_target_name(client: httpx.AsyncClient) -> None:
    response = await client.get(LIST_PATH, params={"q": "db-1"}, headers=bearer())

    assert titles(response) == {"Backup late"}


async def test_search_treats_percent_as_a_literal_character(client: httpx.AsyncClient) -> None:
    response = await client.get(LIST_PATH, params={"q": "100%"}, headers=bearer())

    assert titles(response) == {"Load 100% spike"}


async def test_search_treats_underscore_as_a_literal_character(client: httpx.AsyncClient) -> None:
    response = await client.get(LIST_PATH, params={"q": "_"}, headers=bearer())

    assert titles(response) == {"queue_depth high"}


async def test_blank_search_returns_every_incident(client: httpx.AsyncClient) -> None:
    response = await client.get(LIST_PATH, params={"q": "   "}, headers=bearer())

    assert titles(response) == {title for _, title, _ in SEEDED}


async def test_statuses_filter_accepts_several_values_in_any_case(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        LIST_PATH, params=[("statuses", "new"), ("statuses", "ESCALATED")], headers=bearer()
    )

    assert titles(response) == {
        "Disk almost full",
        "Load 1000 spike",
        "queue_depth high",
        "Service down",
    }


async def test_search_and_statuses_combine(client: httpx.AsyncClient) -> None:
    response = await client.get(
        LIST_PATH,
        params=[("q", "load"), ("statuses", "NEW")],
        headers=bearer(),
    )

    assert titles(response) == {"Load 1000 spike"}


async def test_search_longer_than_100_characters_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.get(LIST_PATH, params={"q": "x" * 101}, headers=bearer())

    assert response.status_code == 422


async def test_a_viewer_can_search_and_filter(
    app: FastAPI, sessions: SessionFactory, seeded: None
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "viewer-user", PASSWORD, Role.VIEWER, "cli")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as http:
        login = await http.post(
            "/api/auth/login", json={"username": "viewer-user", "password": PASSWORD}
        )
        assert login.status_code == 200
        response = await http.get(LIST_PATH, params=[("q", "service"), ("statuses", "ESCALATED")])

    assert titles(response) == {"Service down"}


def bearer() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}
