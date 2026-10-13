from typing import Protocol

from noc.llm.types import LLMRequest, LLMResponse


class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...


class LLMError(Exception):
    pass


class ProviderRateLimited(LLMError):
    pass


class ProviderUnavailable(LLMError):
    pass


class QuotaExhausted(LLMError):
    pass


class ProviderKeyRejected(LLMError):
    pass


class ProviderRequestRejected(LLMError):
    pass


class LLMUnavailable(LLMError):
    pass


class CassetteMiss(LLMError):
    pass


class StructuredOutputError(LLMError):
    pass
