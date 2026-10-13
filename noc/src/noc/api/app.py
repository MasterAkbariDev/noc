from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from noc.api.incidents import router as incidents_router
from noc.config import Settings
from noc.db.session import create_engine, create_session_factory


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        app.state.settings = settings
        app.state.sessions = create_session_factory(engine)
        yield
        await engine.dispose()

    app = FastAPI(title="Multi-Agent NOC", version="0.1.0", lifespan=lifespan)
    app.include_router(incidents_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        async with app.state.sessions() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
