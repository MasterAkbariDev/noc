from typing import Protocol

from noc.llm.types import LLMRequest, LLMResponse


class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...


class LLMError(Exception):
    pass


class ProviderRateLimited(LLMError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnavailable(LLMError):
    pass


class ProviderBadGeneration(ProviderUnavailable):
    pass


class QuotaExhausted(LLMError):
    pass


class ProviderKeyRejected(LLMError):
    pass


class ProviderRequestRejected(LLMError):
    pass


class ProviderModelUnavailable(LLMError):
    """The provider no longer serves this model (retired, renamed or not offered to this key)."""


class LLMUnavailable(LLMError):
    pass


class CassetteMiss(LLMError):
    pass


class StructuredOutputError(LLMError):
    pass


def describe_error(error: BaseException) -> str:
    if not isinstance(error, LLMError):
        return f"{type(error).__name__}: {error}"
    status = getattr(error.__cause__, "status_code", None)
    name = type(error).__name__
    return f"{name} (HTTP {status})" if isinstance(status, int) else name
