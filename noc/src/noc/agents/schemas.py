from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from noc_shared.taxonomy import RootCauseCode

TOOL_REF_PATTERN = r"^T\d+$"
FINDING_ID_PATTERN = r"^F\d+$"


class FindingCategory(StrEnum):
    RESOURCE = "resource"
    SERVICE = "service"
    LOG_PATTERN = "log_pattern"
    NETWORK = "network"
    SECURITY = "security"
    CHANGE = "change"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EvidenceStrength(StrEnum):
    DIRECT = "direct"
    CORRELATED = "correlated"
    CIRCUMSTANTIAL = "circumstantial"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_ref: str = Field(pattern=TOOL_REF_PATTERN)
    excerpt: str = Field(min_length=1, max_length=500)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=FINDING_ID_PATTERN)
    category: FindingCategory
    summary: str = Field(min_length=1, max_length=300)
    severity: FindingSeverity
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=5)
    evidence_strength: EvidenceStrength
    counter_evidence: list[str] = Field(default_factory=list, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    suspected_injection: bool = False


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause_code: RootCauseCode
    description: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_findings: list[str] = Field(default_factory=list)
    contradicting_findings: list[str] = Field(default_factory=list)
    affected_resource_id: str | None = None


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=5)
    is_security_incident: bool = False
    needs_more_info: list[str] = Field(default_factory=list, max_length=5)

    def primary(self) -> Hypothesis:
        return max(self.hypotheses, key=lambda hypothesis: hypothesis.confidence)


class InvestigationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list, max_length=8)
    diagnosis: Diagnosis


class SpecialistReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list, max_length=6)


def unknown_diagnosis(reason: str) -> Diagnosis:
    return Diagnosis(
        hypotheses=[
            Hypothesis(root_cause_code=RootCauseCode.UNKNOWN, description=reason, confidence=0.0)
        ]
    )
