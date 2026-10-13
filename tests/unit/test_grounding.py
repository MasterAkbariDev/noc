from noc.agents.grounding import ground_report
from noc.agents.schemas import InvestigationReport
from noc.tools.registry import ToolResult
from tests.support.builders import investigation_payload

TOOL_OUTPUT = ToolResult(
    ref="T1",
    tool="get_service_status",
    ok=True,
    content=(
        '<tool_result ref="T1">\n{\n "active_state": "failed",\n "restarts": 3\n}\n</tool_result>'
    ),
    data={"active_state": "failed"},
    injection_flags=[],
)


def report(**changes: object) -> InvestigationReport:
    return InvestigationReport.model_validate(investigation_payload(**changes))


def test_quoted_evidence_is_kept() -> None:
    grounded = ground_report(report(), {"T1": TOOL_OUTPUT})
    assert grounded.dropped_findings == 0
    assert grounded.report.diagnosis.primary().root_cause_code == "service_crashed"


def test_invented_quotes_are_dropped_and_diagnosis_becomes_unknown() -> None:
    grounded = ground_report(
        report(excerpt="OOM killer terminated the process"), {"T1": TOOL_OUTPUT}
    )
    assert grounded.dropped_findings == 1
    assert grounded.report.findings == []
    assert grounded.report.diagnosis.primary().root_cause_code == "unknown"


def test_citations_of_unknown_tool_calls_are_dropped() -> None:
    grounded = ground_report(report(), {})
    assert grounded.dropped_findings == 1


def test_whitespace_differences_are_tolerated() -> None:
    grounded = ground_report(report(excerpt='"active_state":   "FAILED"'), {"T1": TOOL_OUTPUT})
    assert grounded.dropped_findings == 0


def test_injection_flags_propagate_to_findings() -> None:
    flagged = ToolResult(**{**TOOL_OUTPUT.__dict__, "injection_flags": ["role_marker"]})
    grounded = ground_report(report(), {"T1": flagged})
    assert grounded.report.findings[0].suspected_injection
