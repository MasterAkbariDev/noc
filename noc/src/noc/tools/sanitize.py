import json
import re
from dataclasses import dataclass
from typing import Any

from noc.llm.redaction import redact

MAX_UNTRUSTED_LINE_CHARS = 500
PROMPT_TAGS = "untrusted_data|tool_result|incident_brief|focus_questions"
TRUNCATION_MARKER = "\n[... truncated by NOC tool layer ...]"

INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"(?i)\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|system)\b"
        r".{0,20}\b(instructions?|prompts?|rules?|messages?)"
    ),
    "role_marker": re.compile(r"(?im)(^|\s)(system|assistant|developer)\s*(override)?\s*:"),
    "persona_override": re.compile(r"(?i)\b(you are now|act as|pretend to be|new instructions)\b"),
    "tool_invocation": re.compile(
        r"(?i)\b(call|run|execute|invoke|use)\b.{0,30}"
        r"\b(restart_service|restart_container|kill_process|block_ip|rollback_release|reboot_host"
        r"|start_service|stop_service|throttle_cpu|limit_memory|vacuum_journal|rotate_logs"
        r"|clean_temp_dir|docker_prune_dangling|tool|function)\b"
    ),
    "tag_escape": re.compile(rf"(?i)<\s*/?\s*({PROMPT_TAGS})"),
    "approval_claim": re.compile(
        r"(?i)\b(admin|administrator|operator|owner)\b.{0,30}\b(approved|authori[sz]ed|allows?)\b"
    ),
    "encoded_blob": re.compile(r"[A-Za-z0-9+/]{160,}={0,2}"),
}

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
TAG_PATTERN = re.compile(rf"(?i)<(\s*/?\s*)({PROMPT_TAGS})")


@dataclass(frozen=True)
class RenderedResult:
    text: str
    truncated: bool
    injection_flags: list[str]


def scan_injection(text: str) -> list[str]:
    return sorted(name for name, pattern in INJECTION_PATTERNS.items() if pattern.search(text))


def neutralize(text: str) -> str:
    text = CONTROL_CHARACTERS.sub(" ", text)
    return TAG_PATTERN.sub(r"[\1\2", text)


def raw_lines(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return [
        item if isinstance(item, str) else json.dumps(item, sort_keys=True, default=str)
        for item in items
    ]


def untrusted_lines(value: Any) -> list[str]:
    return [neutralize(line)[:MAX_UNTRUSTED_LINE_CHARS] for line in raw_lines(value)]


def render_tool_result(
    tool: str,
    ref: str,
    ok: bool,
    data: dict[str, Any] | None,
    error: str | None,
    untrusted_fields: tuple[str, ...],
    max_chars: int,
) -> RenderedResult:
    data = data or {}
    trusted = {key: value for key, value in data.items() if key not in untrusted_fields}
    if error:
        trusted["error"] = error
    sections = [json.dumps(trusted, sort_keys=True, default=str, indent=1)]
    flags: set[str] = set()
    for field_name in untrusted_fields:
        if field_name not in data:
            continue
        for raw_line in raw_lines(data[field_name]):
            flags.update(scan_injection(raw_line))
        body = "\n".join(untrusted_lines(data[field_name]))
        sections.append(
            f'<untrusted_data source="{tool}.{field_name}" ref="{ref}">\n{body}\n</untrusted_data>'
        )

    header = f'<tool_result ref="{ref}" tool="{tool}" ok="{str(ok).lower()}">'
    text = redact("\n".join([header, *sections, "</tool_result>"]), "full").text
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars] + TRUNCATION_MARKER
    return RenderedResult(text=text, truncated=truncated, injection_flags=sorted(flags))
