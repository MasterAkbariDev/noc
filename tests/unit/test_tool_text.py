from noc.reporting.tool_text import evidence_with_sources, tool_text


def test_tools_read_as_plain_descriptions() -> None:
    assert tool_text("get_service_status", {"resource_id": "svc:demo-shop"}) == (
        "Status of demo-shop"
    )
    assert tool_text("get_service_logs", {"resource_id": "svc:demo-shop", "since_minutes": 30}) == (
        "Log of demo-shop, last 30 minutes"
    )
    assert tool_text("query_named_metric", {"query": "cpu_pressure", "window": "1h"}) == (
        "History of cpu pressure, last 1h"
    )
    assert tool_text("get_directory_sizes", {}) == "Folder sizes"
    assert tool_text("brand_new_tool", {}) == "Brand new tool"


def test_evidence_gets_the_source_of_its_tool_call() -> None:
    evidence = [
        {"tool_call_ref": "T1", "excerpt": "inactive"},
        {"tool_call_ref": "T9", "excerpt": "x"},
    ]
    with_sources = evidence_with_sources(evidence, {"T1": "Status of demo-shop"})
    assert with_sources[0]["source"] == "Status of demo-shop"
    assert with_sources[1]["source"] == "a check on the server"
    assert with_sources[0]["excerpt"] == "inactive"
