import re
from dataclasses import dataclass

from noc.agents.schemas import (
    Diagnosis,
    EvidenceRef,
    Finding,
    Hypothesis,
    InvestigationReport,
    unknown_diagnosis,
)
from noc.tools.registry import ToolResult
from noc_shared.taxonomy import RootCauseCode

WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class GroundedReport:
    report: InvestigationReport
    dropped_findings: int
    dropped_evidence: int


def normalize(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip().lower()


def evidence_is_grounded(evidence: EvidenceRef, results: dict[str, ToolResult]) -> bool:
    result = results.get(evidence.tool_call_ref)
    return result is not None and normalize(evidence.excerpt) in normalize(result.content)


def ground_finding(finding: Finding, results: dict[str, ToolResult]) -> Finding | None:
    kept = [evidence for evidence in finding.evidence if evidence_is_grounded(evidence, results)]
    if not kept:
        return None
    cited_flags = any(results[evidence.tool_call_ref].injection_flags for evidence in kept)
    return finding.model_copy(
        update={
            "evidence": kept,
            "suspected_injection": finding.suspected_injection or cited_flags,
        }
    )


def ground_hypothesis(hypothesis: Hypothesis, finding_ids: set[str]) -> Hypothesis | None:
    supporting = [fid for fid in hypothesis.supporting_findings if fid in finding_ids]
    contradicting = [fid for fid in hypothesis.contradicting_findings if fid in finding_ids]
    if hypothesis.root_cause_code is not RootCauseCode.UNKNOWN and not supporting:
        return None
    return hypothesis.model_copy(
        update={"supporting_findings": supporting, "contradicting_findings": contradicting}
    )


def ground_report(report: InvestigationReport, results: dict[str, ToolResult]) -> GroundedReport:
    grounded: list[Finding] = []
    dropped_evidence = 0
    for finding in report.findings:
        checked = ground_finding(finding, results)
        if checked is None:
            dropped_evidence += len(finding.evidence)
            continue
        dropped_evidence += len(finding.evidence) - len(checked.evidence)
        grounded.append(checked)

    finding_ids = {finding.id for finding in grounded}
    hypotheses = [
        kept
        for hypothesis in report.diagnosis.hypotheses
        if (kept := ground_hypothesis(hypothesis, finding_ids)) is not None
    ]
    diagnosis: Diagnosis = (
        report.diagnosis.model_copy(update={"hypotheses": hypotheses})
        if hypotheses
        else unknown_diagnosis("No hypothesis is supported by grounded evidence.")
    )
    return GroundedReport(
        report=InvestigationReport(findings=grounded, diagnosis=diagnosis),
        dropped_findings=len(report.findings) - len(grounded),
        dropped_evidence=dropped_evidence,
    )
