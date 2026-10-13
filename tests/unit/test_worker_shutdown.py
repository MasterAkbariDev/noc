import asyncio
from typing import cast

from noc.config import Settings
from noc.db.session import SessionFactory
from noc.detection.ingest import AlertIngestor
from noc.orchestration.graph import IncidentGraph
from noc.worker.main import Worker, stop_on


class IdleIngestor:
    async def poll_once(self) -> bool:
        return True


async def test_shutdown_event_stops_the_worker_loops() -> None:
    worker = Worker(
        Settings(poll_interval_seconds=0.01),
        sessions=cast(SessionFactory, None),
        graph=cast(IncidentGraph, None),
        ingestor=cast(AlertIngestor, IdleIngestor()),
    )
    shutdown = asyncio.Event()
    watcher = asyncio.create_task(stop_on(shutdown, worker))
    loop = asyncio.create_task(worker.run_ingest_loop())
    await asyncio.sleep(0.05)
    assert not loop.done()
    shutdown.set()
    async with asyncio.timeout(2):
        await asyncio.gather(watcher, loop)
