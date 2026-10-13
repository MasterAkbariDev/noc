import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from noc.db.base import Base
from noc.db.session import SessionFactory, create_engine, create_session_factory


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("NOC_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set NOC_TEST_DATABASE_URL to run integration tests (make test-integration)")
    return url


@pytest_asyncio.fixture
async def sessions(database_url: str) -> AsyncIterator[SessionFactory]:
    engine = create_engine(database_url, pool_size=5)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()
