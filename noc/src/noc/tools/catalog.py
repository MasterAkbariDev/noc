from pydantic import BaseModel

from noc.tools.sentinel_client import SentinelDirectory, SentinelError
from noc.tools.spec import ToolContext, ToolOutput, ToolSpec
from noc_shared.permissions import PermissionClass
from noc_shared.tools import GetServiceStatusArgs

INVESTIGATOR = "investigator"


def traceparent_for(context: ToolContext) -> str:
    return f"00-{context.trace_id}-{context.incident_id.hex[:16]}-01"


def sentinel_read_tool(
    name: str,
    description: str,
    args_model: type[BaseModel],
    agents: frozenset[str],
    sentinels: SentinelDirectory,
    untrusted_fields: tuple[str, ...] = (),
) -> ToolSpec:
    async def handler(args: BaseModel, context: ToolContext) -> ToolOutput:
        client = sentinels.client_for(context.target)
        try:
            response = await client.call_tool(
                name,
                args.model_dump(mode="json"),
                str(context.incident_id),
                traceparent_for(context),
            )
        except SentinelError as exc:
            return ToolOutput(ok=False, error=f"target_unreachable: {exc}")
        if not response.ok:
            message = response.error.message if response.error else "unknown error"
            code = response.error.code if response.error else "INTERNAL"
            return ToolOutput(ok=False, error=f"{code}: {message}")
        return ToolOutput(ok=True, data=response.data)

    return ToolSpec(
        name=name,
        description=description,
        args_model=args_model,
        permission=PermissionClass.READ_ONLY,
        agents=agents,
        handler=handler,
        untrusted_fields=untrusted_fields,
    )


def build_read_tools(sentinels: SentinelDirectory) -> list[ToolSpec]:
    return [
        sentinel_read_tool(
            name="get_service_status",
            description=(
                "Read the systemd state of one registered service on the incident's target: "
                "active/sub state, restart count, main process exit status, active since, memory."
            ),
            args_model=GetServiceStatusArgs,
            agents=frozenset({INVESTIGATOR}),
            sentinels=sentinels,
        ),
    ]
