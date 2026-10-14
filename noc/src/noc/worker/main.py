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
from noc.db.base import utc_now
from noc.db.session import SessionFactory, create_engine, create_session_factory, transaction
from noc.detection.alerts import PrometheusAlertSource
from noc.detection.correlator import INVESTIGATE_JOB
from noc.detection.file_sd import refresh_file_sd
from noc.detection.ingest import AlertIngestor
from noc.domain.incident_status import EscalationReason
from noc.domain.variants import ModePolicy
from noc.jobs import queue
from noc.jobs.queue import ClaimedJob
from noc.llm.client import describe_error
from noc.orchestration.graph import (
    IncidentGraph,
    build_incident_graph,
    build_remediation_graph,
    run_incident,
)
from noc.orchestration.runtime import build_runtime
from noc.store.incidents import escalate_abandoned
from noc.store.investigations import fail_orphaned_runs
from noc.store.remediation import REMEDIATE_JOB, expire_approvals
from noc.tools.sentinel_client import build_sentinel_http
from noc.worker.heartbeat import PollStatus, write_heartbeat

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
PROMETHEUS_POLL_FAILED = "Prometheus did not answer the alert poll"
ORPHAN_SWEEP_SECONDS = 60.0


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class Worker:
    def __init__(
        self,
        settings: Settings,
        sessions: SessionFactory,
        graph: IncidentGraph,
        ingestor: AlertIngestor,
        remediation_graph: IncidentGraph | None = None,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._graph = graph
        self._remediation_graph = remediation_graph
        self._ingestor = ingestor
        self._identity = worker_identity()
        self._started_at = utc_now()
        self._poll = PollStatus()
        self._slots = asyncio.Semaphore(settings.max_concurrent_incidents)
        self._stopping = asyncio.Event()
        self._running: set[asyncio.Task[None]] = set()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        loops: list[Awaitable[None]] = [
            self.run_ingest_loop(),
            self.run_heartbeat_loop(),
            self.run_orphan_sweep_loop(),
            self._job_loop(),
        ]
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
        await self._repeat("ingest", self._poll_alerts, self._settings.poll_interval_seconds)

    async def _poll_alerts(self) -> None:
        try:
            polled = await self._ingestor.poll_once()
        except Exception as exc:
            self._poll.failed(utc_now(), type(exc).__name__)
            raise
        if polled:
            self._poll.ok(utc_now())
        else:
            self._poll.failed(utc_now(), PROMETHEUS_POLL_FAILED)

    async def run_heartbeat_loop(self) -> None:
        await self._repeat("heartbeat", self.beat_once, self._settings.worker_heartbeat_seconds)

    async def beat_once(self) -> None:
        async with transaction(self._sessions) as session:
            await write_heartbeat(
                session,
                self._identity,
                self._started_at,
                self._poll,
                self._settings.version,
                utc_now(),
            )

    async def run_orphan_sweep_loop(self) -> None:
        await self._repeat("orphans", self.sweep_orphans_once, ORPHAN_SWEEP_SECONDS)

    async def sweep_orphans_once(self) -> int:
        async with transaction(self._sessions) as session:
            failed = await fail_orphaned_runs(session, INVESTIGATE_JOB)
            expired = await expire_approvals(session)
        if expired:
            logger.warning("approvals_expired", count=expired)
        if failed:
            logger.warning("orphaned_agent_runs_failed", count=failed)
        return failed

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
                session, self._identity, self._job_kinds(), self._settings.job_lease_seconds
            )

    def _job_kinds(self) -> list[str]:
        if self._remediation_graph is None:
            return [INVESTIGATE_JOB]
        return [INVESTIGATE_JOB, REMEDIATE_JOB]

    async def _run_job(self, job: ClaimedJob) -> None:
        incident_id = uuid.UUID(job.payload["incident_id"])
        if job.kind == REMEDIATE_JOB and self._remediation_graph is not None:
            await run_incident(self._remediation_graph, incident_id, job.payload["action_id"])
            return
        await run_incident(self._graph, incident_id)

    async def _handle(self, job: ClaimedJob) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        try:
            await self._run_job(job)
        except Exception as exc:
            logger.exception("job_failed", job_id=job.id, kind=job.kind)
            error = describe_error(exc)
            async with transaction(self._sessions) as session:
                await queue.fail(session, job.id, self._identity, error, RETRY_DELAY_SECONDS)
                if await queue.is_dead(session, job.id):
                    await escalate_abandoned(
                        session,
                        uuid.UUID(job.payload["incident_id"]),
                        EscalationReason.INVESTIGATION_FAILED,
                        error[:500],
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


async def run_logged(worker: Worker) -> None:
    logger.info("worker_started", identity=worker_identity())
    await worker.run()
    logger.info("worker_stopped", identity=worker_identity())


async def stop_on(shutdown: asyncio.Event, worker: Worker) -> None:
    await shutdown.wait()
    worker.stop()


async def run_worker(settings: Settings, shutdown: asyncio.Event | None = None) -> None:
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
        runtime = build_runtime(
            settings,
            sessions,
            sentinel_http,
            prometheus_http=prometheus_http,
            prometheus_url=settings.prometheus_url,
        )
        graph = build_incident_graph(runtime, checkpointer)
        remediation_graph = build_remediation_graph(runtime, checkpointer)
        source = PrometheusAlertSource(prometheus_http, settings.prometheus_url)
        ingestor = AlertIngestor(
            source,
            sessions,
            settings.missing_polls_to_resolve,
            ModePolicy(default=settings.agent_mode, honour_override=settings.eval_mode),
        )
        worker = Worker(settings, sessions, graph, ingestor, remediation_graph)
        if shutdown is None:
            loop = asyncio.get_running_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, worker.stop)
            await run_logged(worker)
        else:
            watcher = asyncio.create_task(stop_on(shutdown, worker))
            await run_logged(worker)
            watcher.cancel()
    await engine.dispose()
