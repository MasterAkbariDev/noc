import asyncio

import uvicorn

from noc.api.app import create_app
from noc.config import Settings
from noc.worker.main import run_worker


async def run_all_in_one(settings: Settings, host: str, port: int) -> None:
    shutdown = asyncio.Event()
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host=host, port=port, proxy_headers=False)
    )
    worker = asyncio.create_task(run_worker(settings, shutdown))
    try:
        await server.serve()
    finally:
        shutdown.set()
        await worker
