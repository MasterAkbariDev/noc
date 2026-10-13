import asyncio
import json

from pydantic import BaseModel

from noc.tools.recorder import MemoryToolCallRecorder
from noc.tools.registry import ToolRegistry
from noc.tools.spec import ToolContext, ToolOutput, ToolSpec
from noc_shared.permissions import PermissionClass
from noc_shared.tools import GetServiceStatusArgs
from tests.support.builders import tool_context


async def status_handler(args: BaseModel, context: ToolContext) -> ToolOutput:
    return ToolOutput(ok=True, data={"active_state": "failed"})


async def slow_handler(args: BaseModel, context: ToolContext) -> ToolOutput:
    await asyncio.sleep(1)
    return ToolOutput(ok=True, data={})


def spec(name: str = "get_service_status", **changes: object) -> ToolSpec:
    values: dict[str, object] = {
        "name": name,
        "description": "status",
        "args_model": GetServiceStatusArgs,
        "permission": PermissionClass.READ_ONLY,
        "agents": frozenset({"investigator"}),
        "handler": status_handler,
        **changes,
    }
    return ToolSpec(**values)


ARGS = json.dumps({"resource_id": "svc:demo-shop"})


async def test_successful_call_is_recorded_with_a_ref() -> None:
    recorder = MemoryToolCallRecorder()
    result = await ToolRegistry([spec()], recorder).execute(
        "get_service_status", ARGS, tool_context()
    )
    assert result.ok
    assert result.ref == "T1"
    assert '"active_state": "failed"' in result.content
    assert recorder.records[0].decision == "allowed"


async def test_agent_cannot_use_tools_outside_its_allow_list() -> None:
    recorder = MemoryToolCallRecorder()
    registry = ToolRegistry([spec()], recorder)
    result = await registry.execute("get_service_status", ARGS, tool_context(agent="logs"))
    assert not result.ok
    assert recorder.records[0].decision == "denied"
    assert registry.schemas_for("logs") == []


async def test_action_permissions_are_refused_even_if_registered() -> None:
    registry = ToolRegistry(
        [spec(permission=PermissionClass.SAFE_ACTION)], MemoryToolCallRecorder()
    )
    result = await registry.execute("get_service_status", ARGS, tool_context())
    assert not result.ok
    assert "cannot be called by an agent" in result.content


async def test_invalid_and_unparseable_arguments_never_reach_the_handler() -> None:
    registry = ToolRegistry([spec()], MemoryToolCallRecorder())
    invalid = await registry.execute(
        "get_service_status", '{"resource_id": "rm -rf /"}', tool_context()
    )
    garbage = await registry.execute("get_service_status", "{not json", tool_context())
    assert not invalid.ok
    assert not garbage.ok


async def test_unknown_tools_are_denied_and_recorded() -> None:
    recorder = MemoryToolCallRecorder()
    result = await ToolRegistry([spec()], recorder).execute("run_command", "{}", tool_context())
    assert not result.ok
    assert recorder.records[0].permission == "UNKNOWN"


async def test_slow_tools_time_out() -> None:
    registry = ToolRegistry(
        [spec(handler=slow_handler, timeout_seconds=0.05)], MemoryToolCallRecorder()
    )
    result = await registry.execute("get_service_status", ARGS, tool_context())
    assert not result.ok
    assert "timed out" in result.content
