import asyncio
import time
from collections.abc import Callable

import structlog

from noc.config import Settings
from noc.db.session import SessionFactory
from noc.llm.client import LLMClient
from noc.llm.keys import KeyEntry, all_keys, config_version, proxy_settings
from noc.llm.providers import load_providers
from noc.llm.types import LLMRequest, LLMResponse
from noc.secret_store import SecretStore

logger = structlog.get_logger(__name__)

Builder = Callable[[list[KeyEntry], dict[str, str | None]], LLMClient]


class ReloadingLLM:
    def __init__(
        self,
        settings: Settings,
        sessions: SessionFactory,
        store: SecretStore,
        build: Builder,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._store = store
        self._build = build
        self._clock = clock
        self._lock = asyncio.Lock()
        self._client: LLMClient | None = None
        self._version: str | None = None
        self._checked_at = float("-inf")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = await self.current()
        return await client.complete(request)

    async def current(self) -> LLMClient:
        if self._client is not None and not self._due():
            return self._client
        async with self._lock:
            if self._client is None or self._due():
                await self._refresh()
        assert self._client is not None
        return self._client

    def _due(self) -> bool:
        return self._clock() - self._checked_at >= self._settings.llm_reload_seconds

    async def _refresh(self) -> None:
        document = load_providers(self._settings.llm_providers_file)
        async with self._sessions() as session:
            version = await config_version(session)
            if self._client is not None and version == self._version:
                self._checked_at = self._clock()
                return
            keys = await all_keys(session, self._store, document)
            proxies = await proxy_settings(session, self._store, document)
        self._client = self._build(keys, {name: proxy.url for name, proxy in proxies.items()})
        self._version = version
        self._checked_at = self._clock()
        logger.info("llm_config_loaded", keys=len(keys), version=version)
