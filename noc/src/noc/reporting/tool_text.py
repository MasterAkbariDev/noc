from collections.abc import Mapping
from typing import Any, Final

from noc.reporting.event_text import resource_name

TOOL_TEXT: Final[dict[str, str]] = {
    "get_service_status": "Status of {resource}",
    "get_service_logs": "Log of {resource}{window}",
    "get_cpu_usage": "CPU use on the server",
    "get_memory_usage": "Memory use on the server",
    "get_disk_usage": "Disk space on the server",
    "get_top_processes": "Busiest programs on the server",
    "get_directory_sizes": "Folder sizes{path}",
    "get_listening_ports": "Open network ports",
    "get_network_stats": "Network traffic counters",
    "get_connection_summary": "Open network connections",
    "get_auth_events": "Login attempts{window}",
    "get_active_sessions": "Who is logged in",
    "get_host_overview": "Server overview (CPU, memory, disk)",
    "query_named_metric": "History of {query}{window}",
}


def window_text(args: Mapping[str, Any]) -> str:
    if "since_minutes" in args:
        return f", last {args['since_minutes']} minutes"
    if "window" in args:
        return f", last {args['window']}"
    return ""


def tool_text(tool: str, args: Mapping[str, Any]) -> str:
    template = TOOL_TEXT.get(tool)
    if template is None:
        return tool.replace("_", " ").capitalize()
    query = str(args.get("query", "a metric")).replace("_", " ")
    return template.format(
        resource=resource_name(args.get("resource_id")) or "a service",
        window=window_text(args),
        path=f" in {args['path']}" if args.get("path") else "",
        query=query,
    )


def evidence_with_sources(
    evidence: list[dict[str, Any]], sources: Mapping[str, str]
) -> list[dict[str, Any]]:
    return [
        {**item, "source": sources.get(str(item.get("tool_call_ref")), "a check on the server")}
        for item in evidence
    ]
