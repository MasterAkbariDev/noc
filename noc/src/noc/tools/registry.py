import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from noc.db.base import utc_now
from noc.llm.types import ToolSchema
from noc.policy.engine import tool_call_allowed
from noc.tools.recorder import ToolCallRecord, ToolCallRecorder
from noc.tools.sanitize import render_tool_result
from noc.tools.spec import ToolContext, ToolOutput, ToolSpec


@dataclass(frozen=True)
class ToolResult:
    ref: str
    tool: str
    ok: bool
    content: str
    data: dict[str, Any] | None
    injection_flags: list[str]


@dataclass(frozen=True)
class Outcome:
    output: ToolOutput
    decision: str
    reason: str


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec], recorder: ToolCallRecorder) -> None:
        self._specs = {spec.name: spec for spec in specs}
        self._recorder = recorder

    def names_for(self, agent: str) -> list[str]:
        return sorted(name for name, spec in self._specs.items() if agent in spec.agents)

    def schemas_for(self, agent: str) -> list[ToolSchema]:
        return [self._specs[name].llm_schema() for name in self.names_for(agent)]

    async def execute(self, name: str, raw_arguments: str, context: ToolContext) -> ToolResult:
        started_at = utc_now()
        clock = time.monotonic()
        spec = self._specs.get(name)
        arguments = parse_arguments(raw_arguments)
        outcome = await self._run(spec, name, arguments, context)
        ref = await self._recorder.next_ref(context)
        rendered = render_tool_result(
            tool=name,
            ref=ref,
            ok=outcome.output.ok,
            data=outcome.output.data,
            error=outcome.output.error,
            untrusted_fields=spec.untrusted_fields if spec else (),
            max_chars=spec.max_result_chars if spec else 2_000,
        )
        await self._recorder.record(
            ToolCallRecord(
                ref=ref,
                context=context,
                tool=name,
                args=arguments,
                permission=spec.permission.name if spec else "UNKNOWN",
                decision=outcome.decision,
                decision_reason=outcome.reason,
                ok=outcome.output.ok,
                started_at=started_at,
                duration_ms=int((time.monotonic() - clock) * 1000),
                result=outcome.output.data,
                result_text=rendered.text,
                truncated=rendered.truncated,
                injection_flags=rendered.injection_flags,
            )
        )
        return ToolResult(
            ref=ref,
            tool=name,
            ok=outcome.output.ok,
            content=rendered.text,
            data=outcome.output.data,
            injection_flags=rendered.injection_flags,
        )

    async def _run(
        self, spec: ToolSpec | None, name: str, arguments: dict[str, Any], context: ToolContext
    ) -> Outcome:
        if spec is None or context.agent not in spec.agents:
            return denied(f"tool {name} is not available to agent {context.agent}", "not_allowed")
        allowed, reason = tool_call_allowed(spec.permission)
        if not allowed:
            return denied(f"tool {name} cannot be called by an agent", reason)
        try:
            args = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            return denied(f"invalid arguments: {exc.errors()[0]['msg']}", "invalid_arguments")
        try:
            async with asyncio.timeout(spec.timeout_seconds):
                output = await spec.handler(args, context)
        except TimeoutError:
            output = ToolOutput(ok=False, error="tool timed out")
        return Outcome(output=output, decision="allowed", reason=reason)


def parse_arguments(raw_arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {"_unparseable": raw_arguments[:200]}
    return parsed if isinstance(parsed, dict) else {"_value": parsed}


def denied(message: str, reason: str) -> Outcome:
    return Outcome(output=ToolOutput(ok=False, error=message), decision="denied", reason=reason)
