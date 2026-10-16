from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from noc.api.activity import router as activity_router
from noc.api.auth import router as auth_router
from noc.api.events import router as events_router
from noc.api.incidents import router as incidents_router
from noc.api.live_metrics import router as live_router
from noc.api.llm_admin import router as llm_admin_router
from noc.api.metrics import router as metrics_router
from noc.api.notifications import router as notifications_router
from noc.api.overview import router as overview_router
from noc.api.prometheus import PrometheusReader
from noc.api.servers import router as servers_router
from noc.api.spa import SinglePageApp
from noc.api.story import router as story_router
from noc.api.system import router as system_router
from noc.api.system_llm import router as system_llm_router
from noc.api.targets import router as targets_router
from noc.api.tickets import TicketStore, redact_tickets_in_access_log
from noc.api.trace import router as trace_router
from noc.api.users import router as users_router
from noc.config import Settings
from noc.db.session import create_engine, create_session_factory

PROMETHEUS_READ_TIMEOUT_SECONDS = 3.0
COMPRESSION_MINIMUM_BYTES = 1024


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        app.state.settings = settings
        app.state.sessions = create_session_factory(engine)
        app.state.tickets = TicketStore()
        async with httpx.AsyncClient(timeout=PROMETHEUS_READ_TIMEOUT_SECONDS) as prometheus_http:
            app.state.prometheus = PrometheusReader(prometheus_http, settings.prometheus_url)
            yield
        await engine.dispose()

    redact_tickets_in_access_log()
    app = FastAPI(
        title="Multi-Agent NOC",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(GZipMiddleware, minimum_size=COMPRESSION_MINIMUM_BYTES)
    app.include_router(auth_router)
    app.include_router(incidents_router)
    app.include_router(trace_router)
    app.include_router(story_router)
    app.include_router(events_router)
    app.include_router(targets_router)
    app.include_router(servers_router)
    app.include_router(system_llm_router)
    app.include_router(system_router)
    app.include_router(activity_router)
    app.include_router(overview_router)
    app.include_router(users_router)
    app.include_router(llm_admin_router)
    app.include_router(notifications_router)
    app.include_router(metrics_router)
    app.include_router(live_router)

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

    if settings.frontend_dist is not None and settings.frontend_dist.is_dir():
        app.mount("/", SinglePageApp(directory=settings.frontend_dist, html=True), name="frontend")

    return app
