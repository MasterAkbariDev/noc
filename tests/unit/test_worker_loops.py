import asyncio
from typing import cast

from noc.config import Settings
from noc.db.session import SessionFactory
from noc.detection.ingest import AlertIngestor
from noc.orchestration.graph import IncidentGraph
from noc.worker.main import Worker


class FlakyIngestor:
    def __init__(self) -> None:
        self.calls = 0
        self.worker: Worker | None = None

    async def poll_once(self) -> bool:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("database went away")
        if self.worker is not None:
            self.worker.stop()
        return True


async def test_an_error_in_a_loop_does_not_stop_the_worker() -> None:
    ingestor = FlakyIngestor()
    worker = Worker(
        Settings(poll_interval_seconds=0.01),
        sessions=cast(SessionFactory, None),
        graph=cast(IncidentGraph, None),
        ingestor=cast(AlertIngestor, ingestor),
    )
    ingestor.worker = worker
    async with asyncio.timeout(2):
        await worker.run_ingest_loop()
    assert ingestor.calls == 2
