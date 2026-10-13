import hashlib
import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass

from noc.llm.client import LLMClient
from noc.llm.types import ChatMessage, LLMRequest, LLMResponse, Role

REDACTED = "[REDACTED]"

Rule = tuple[re.Pattern[str], Callable[[re.Match[str]], str]]


def replace_with(value: str) -> Callable[[re.Match[str]], str]:
    return lambda _match: value


def keep_prefix(match: re.Match[str]) -> str:
    return f"{match.group(1)}{REDACTED}"


SECRET_RULES: list[Rule] = [
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        replace_with("[REDACTED PRIVATE KEY]"),
    ),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/-]+=*"), keep_prefix),
    (
        re.compile(r"(?i)(\w*(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[=:]\s*)\S+"),
        keep_prefix,
    ),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), replace_with("[REDACTED JWT]")),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), replace_with("[REDACTED AWS KEY]")),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), replace_with("[REDACTED GOOGLE KEY]")),
    (re.compile(r"\b(?:sk|gsk)_?-?[A-Za-z0-9]{20,}\b"), replace_with("[REDACTED API KEY]")),
    (
        re.compile(r"(\b[a-z][a-z0-9+.-]*://[^:/\s@]+:)[^@\s]+@"),
        lambda m: f"{m.group(1)}{REDACTED}@",
    ),
]

EMAIL_RULE: Rule = (
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    replace_with("[EMAIL]"),
)

IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def pseudonymize_public_ip(match: re.Match[str]) -> str:
    candidate = match.group(0)
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return candidate
    if not address.is_global:
        return candidate
    return "ip-" + hashlib.sha256(candidate.encode()).hexdigest()[:8]


@dataclass(frozen=True)
class RedactionResult:
    text: str
    replacements: int


def redact(text: str, data_policy: str) -> RedactionResult:
    rules = list(SECRET_RULES)
    if data_policy != "full":
        rules += [EMAIL_RULE, (IPV4_PATTERN, pseudonymize_public_ip)]
    replacements = 0
    for pattern, replacement in rules:
        text, count = pattern.subn(replacement, text)
        replacements += count
    return RedactionResult(text, replacements)


class RedactingLLM:
    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner

    async def complete(self, request: LLMRequest) -> LLMResponse:
        total = 0
        messages: list[ChatMessage] = []
        for message in request.messages:
            if message.role is Role.SYSTEM or message.content is None:
                messages.append(message)
                continue
            result = redact(message.content, request.context.data_policy)
            total += result.replacements
            messages.append(message.model_copy(update={"content": result.text}))
        response = await self._inner.complete(request.model_copy(update={"messages": messages}))
        response.redactions = total
        return response
