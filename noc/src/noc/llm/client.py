import re
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


KEY_SHAPES: re.Pattern[str] = re.compile(r"(gsk_|AIza|AQ\.|sk-)[A-Za-z0-9_\-]+")


def redact_keys(text: str) -> str:
    return KEY_SHAPES.sub("[key]", text)


def describe_error(error: BaseException) -> str:
    if not isinstance(error, LLMError):
        return f"{type(error).__name__}: {error}"
    status = getattr(error.__cause__, "status_code", None)
    name = type(error).__name__
    if not isinstance(status, int):
        return name
    # The provider's message says why it refused the request, so keep it, without any key.
    return f"{name} (HTTP {status}): {redact_keys(str(error))}"[:500]
