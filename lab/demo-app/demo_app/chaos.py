import threading
from collections.abc import Callable
from typing import Final

from fastapi import FastAPI
from pydantic import BaseModel, Field

LEAK_CHUNK_BYTES: Final = 1024 * 1024
MIB: Final = 1024 * 1024


class ChaosSettings(BaseModel):
    memory_leak: bool = False
    upstream_delay_ms: int = Field(default=0, ge=0, le=30000)
    connection_leak: bool = False


class ChaosStatus(ChaosSettings):
    leaked_memory_mib: int


class ChaosState:
    def __init__(self) -> None:
        self.settings = ChaosSettings()
        self._leaked_chunks: list[bytearray] = []

    def leak_memory_if_enabled(self, chunks: int = 1) -> None:
        if self.settings.memory_leak:
            self._leaked_chunks.extend(bytearray(LEAK_CHUNK_BYTES) for _ in range(chunks))

    def status(self) -> ChaosStatus:
        leaked_mib = len(self._leaked_chunks) * LEAK_CHUNK_BYTES // MIB
        return ChaosStatus(**self.settings.model_dump(), leaked_memory_mib=leaked_mib)

    def replace_settings(self, settings: ChaosSettings) -> None:
        self.settings = settings

    def reset(self) -> None:
        self.settings = ChaosSettings()
        self._leaked_chunks.clear()


def build_chaos_app(state: ChaosState, on_reset: Callable[[], None]) -> FastAPI:
    app = FastAPI(title="demo-app chaos", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/chaos")
    def read_chaos() -> ChaosStatus:
        return state.status()

    @app.put("/chaos")
    def write_chaos(settings: ChaosSettings) -> ChaosStatus:
        state.replace_settings(settings)
        return state.status()

    @app.post("/chaos/reset")
    def reset_chaos() -> ChaosStatus:
        state.reset()
        on_reset()
        return state.status()

    return app


class MemoryLeaker:
    def __init__(self, state: ChaosState, mib_per_tick: int, interval_seconds: float) -> None:
        self._state = state
        self._mib_per_tick = mib_per_tick
        self._interval_seconds = interval_seconds
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="memory-leaker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._thread.join(timeout=5)

    def tick(self) -> None:
        self._state.leak_memory_if_enabled(self._mib_per_tick)

    def _run(self) -> None:
        while not self._stopping.wait(self._interval_seconds):
            self.tick()
