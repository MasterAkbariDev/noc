import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.registry import CollectorRegistry

from noc_sentinel.action_store import ActionStore
from noc_sentinel.actions import (
    ActionExecutor,
    ActionRunner,
    SubprocessActionRunner,
    build_actions_router,
)
from noc_sentinel.chaos import (
    ChaosController,
    ChaosRunner,
    SubprocessChaosRunner,
    build_chaos_router,
)
from noc_sentinel.config import SENTINEL_VERSION, SentinelConfig
from noc_sentinel.halt import is_halted
from noc_sentinel.metrics import SentinelCollector
from noc_sentinel.nonce_store import NonceStore
from noc_sentinel.security import RequestVerifier
from noc_sentinel.tools import Toolbox
from noc_sentinel.tools.auth import (
    AuthLogReader,
    PsutilSessionReader,
    SessionReader,
    SubprocessAuthLog,
)
from noc_sentinel.tools.disk_breakdown import DiskBreakdownReader, FilesystemDiskBreakdown
from noc_sentinel.tools.host import HostReader, PsutilHostReader
from noc_sentinel.tools.journal import JournalReader, SubprocessJournal
from noc_sentinel.tools.network import NetworkReader, PsutilNetworkReader
from noc_sentinel.tools.systemd import SystemctlRunner
from noc_shared.resources import Inventory
from noc_shared.signing import VerifiedRequest
from noc_shared.tools import ToolCallRequest, ToolCallResponse


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(
    config: SentinelConfig,
    systemctl: SystemctlRunner,
    nonce_store: NonceStore,
    secrets: dict[str, bytes],
    clock: Callable[[], datetime] = utc_now,
    host: HostReader | None = None,
    journal: JournalReader | None = None,
    chaos_runner: ChaosRunner | None = None,
    action_runner: ActionRunner | None = None,
    disk_breakdown: DiskBreakdownReader | None = None,
    network: NetworkReader | None = None,
    auth_log: AuthLogReader | None = None,
    sessions: SessionReader | None = None,
) -> FastAPI:
    app = FastAPI(title="noc-sentinel", version=SENTINEL_VERSION, docs_url=None, redoc_url=None)

    @app.exception_handler(RequestValidationError)
    def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        problems = [
            {"loc": [str(part) for part in item["loc"]], "msg": str(item["msg"])}
            for item in error.errors()
        ]
        return JSONResponse({"detail": problems}, status_code=422)

    verifier = RequestVerifier(secrets, nonce_store, clock, config.max_skew_seconds)
    toolbox = Toolbox(
        config,
        systemctl,
        host if host is not None else PsutilHostReader(),
        journal if journal is not None else SubprocessJournal(),
        disk_breakdown if disk_breakdown is not None else FilesystemDiskBreakdown(),
        network if network is not None else PsutilNetworkReader(),
        auth_log if auth_log is not None else SubprocessAuthLog(),
        sessions if sessions is not None else PsutilSessionReader(),
    )
    chaos_mounted = config.environment == "lab" and config.chaos.enabled
    if chaos_mounted:
        chaos_verifier = RequestVerifier(
            config.load_chaos_secrets(), nonce_store, clock, config.max_skew_seconds
        )
        controller = ChaosController(
            config, chaos_runner if chaos_runner is not None else SubprocessChaosRunner(), clock
        )
        app.include_router(build_chaos_router(controller, chaos_verifier))
    if config.actions.enabled:
        executor = ActionExecutor(
            config,
            systemctl,
            action_runner if action_runner is not None else SubprocessActionRunner(),
            ActionStore(config.state_dir / "actions.db"),
            clock,
            time.sleep,
        )
        app.include_router(build_actions_router(executor, verifier))
    registry = CollectorRegistry()
    registry.register(SentinelCollector(config, systemctl, chaos_enabled=chaos_mounted))
    Signed = Annotated[VerifiedRequest, Depends(verifier)]

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/inventory")
    def inventory(_: Signed) -> Inventory:
        return Inventory(
            target=config.target,
            environment=config.environment,
            sentinel_version=SENTINEL_VERSION,
            halted=is_halted(config.halt_file),
            resources=config.resources,
        )

    @app.post("/v1/tools/{tool_name}")
    def call_tool(tool_name: str, request: ToolCallRequest, _: Signed) -> ToolCallResponse:
        return toolbox.run(tool_name, request.args)

    @app.get("/v1/tools")
    def list_tools(_: Signed) -> dict[str, Any]:
        return {"tools": toolbox.names()}

    return app
