import asyncio
import os
import signal
import socket
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path

import httpx
import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from prometheus_client import Counter, start_http_server

from noc.config import Settings
from noc.db.session import SessionFactory, create_engine, create_session_factory, transaction
from noc.detection.alerts import PrometheusAlertSource
from noc.detection.correlator import INVESTIGATE_JOB
from noc.detection.file_sd import refresh_file_sd
from noc.detection.ingest import AlertIngestor
from noc.jobs import queue
from noc.jobs.queue import ClaimedJob
from noc.orchestration.graph import IncidentGraph, build_incident_graph, run_incident
from noc.orchestration.runtime import build_runtime
from noc.tools.sentinel_client import build_sentinel_http

logger = structlog.get_logger(__name__)

JOBS_FINISHED = Counter(
    "noc_jobs_finished_total", "Jobs finished by the worker", ["kind", "result"]
)
LOOP_ERRORS = Counter(
    "noc_worker_loop_errors_total", "Unexpected errors caught in worker loops", ["loop"]
)
RETRY_DELAY_SECONDS = 30
IDLE_SLEEP_SECONDS = 1.0
ERROR_BACKOFF_SECONDS = 5.0


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class Worker:
    def __init__(
        self,
        settings: Settings,
        sessions: SessionFactory,
        graph: IncidentGraph,
        ingestor: AlertIngestor,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._graph = graph
        self._ingestor = ingestor
        self._identity = worker_identity()
        self._slots = asyncio.Semaphore(settings.max_concurrent_incidents)
        self._stopping = asyncio.Event()
        self._running: set[asyncio.Task[None]] = set()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        loops: list[Awaitable[None]] = [self.run_ingest_loop(), self._job_loop()]
        if self._settings.prometheus_targets_dir is not None:
            loops.append(self._file_sd_loop(self._settings.prometheus_targets_dir))
        await asyncio.gather(*loops)
        if self._running:
            await asyncio.wait(self._running)

    async def _sleep(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), seconds)

    async def _repeat(
        self, name: str, step: Callable[[], Awaitable[object]], interval_seconds: float
    ) -> None:
        while not self._stopping.is_set():
            try:
                await step()
            except Exception:
                LOOP_ERRORS.labels(name).inc()
                logger.exception("worker_loop_error", loop=name)
            await self._sleep(interval_seconds)

    async def run_ingest_loop(self) -> None:
        await self._repeat("ingest", self._ingestor.poll_once, self._settings.poll_interval_seconds)

    async def _file_sd_loop(self, directory: Path) -> None:
        await self._repeat(
            "file_sd",
            lambda: refresh_file_sd(self._sessions, directory),
            self._settings.file_sd_interval_seconds,
        )

    async def _job_loop(self) -> None:
        while not self._stopping.is_set():
            await self._slots.acquire()
            try:
                job = await self._claim()
            except Exception:
                self._slots.release()
                LOOP_ERRORS.labels("claim").inc()
                logger.exception("worker_loop_error", loop="claim")
                await self._sleep(ERROR_BACKOFF_SECONDS)
                continue
            if job is None:
                self._slots.release()
                await self._sleep(IDLE_SLEEP_SECONDS)
                continue
            task = asyncio.create_task(self._handle(job))
            self._running.add(task)
            task.add_done_callback(self._running.discard)

    async def _claim(self) -> ClaimedJob | None:
        async with transaction(self._sessions) as session:
            return await queue.claim(
                session, self._identity, [INVESTIGATE_JOB], self._settings.job_lease_seconds
            )

    async def _handle(self, job: ClaimedJob) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        try:
            await run_incident(self._graph, uuid.UUID(job.payload["incident_id"]))
        except Exception as exc:
            logger.exception("job_failed", job_id=job.id, kind=job.kind)
            async with transaction(self._sessions) as session:
                await queue.fail(
                    session,
                    job.id,
                    self._identity,
                    f"{type(exc).__name__}: {exc}",
                    RETRY_DELAY_SECONDS,
                )
            JOBS_FINISHED.labels(job.kind, "failed").inc()
        else:
            async with transaction(self._sessions) as session:
                await queue.complete(session, job.id, self._identity)
            JOBS_FINISHED.labels(job.kind, "done").inc()
        finally:
            heartbeat.cancel()
            self._slots.release()

    async def _heartbeat(self, job_id: int) -> None:
        interval = self._settings.job_lease_seconds / 3
        while True:
            await asyncio.sleep(interval)
            async with transaction(self._sessions) as session:
                await queue.heartbeat(
                    session, job_id, self._identity, self._settings.job_lease_seconds
                )


async def run_worker(settings: Settings) -> None:
    start_http_server(settings.worker_metrics_port)
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    sentinel_http = build_sentinel_http(
        settings.sentinel_ca_file,
        settings.sentinel_client_cert,
        settings.sentinel_client_key,
        settings.sentinel_timeout_seconds,
    )
    async with (
        AsyncPostgresSaver.from_conn_string(settings.libpq_url) as checkpointer,
        httpx.AsyncClient() as prometheus_http,
        sentinel_http,
    ):
        await checkpointer.setup()
        runtime = build_runtime(settings, sessions, sentinel_http)
        graph = build_incident_graph(runtime, checkpointer)
        source = PrometheusAlertSource(prometheus_http, settings.prometheus_url)
        ingestor = AlertIngestor(source, sessions, settings.missing_polls_to_resolve)
        worker = Worker(settings, sessions, graph, ingestor)
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, worker.stop)
        logger.info("worker_started", identity=worker_identity())
        await worker.run()
    await engine.dispose()
