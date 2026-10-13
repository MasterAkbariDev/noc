from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from noc_shared.resources import ResourceId
from noc_shared.taxonomy import RootCauseCode

SCENARIO_NAME_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class Injection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["service_down"]
    resource_id: ResourceId
    ttl_seconds: int = Field(ge=1)


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause_code: RootCauseCode
    resource_id: ResourceId
    acceptable_actions: list[str]
    expected_outcome: Literal["escalated", "resolved", "self_resolved"]


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=SCENARIO_NAME_PATTERN, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    injection: Injection
    detection_timeout_seconds: int = Field(default=240, ge=1)
    outcome_timeout_seconds: int = Field(default=600, ge=1)
    ground_truth: GroundTruth

    @model_validator(mode="after")
    def check_timing_and_ground_truth(self) -> Self:
        if self.injection.ttl_seconds < self.detection_timeout_seconds:
            raise ValueError("injection ttl_seconds must cover detection_timeout_seconds")
        if self.ground_truth.resource_id != self.injection.resource_id:
            raise ValueError("ground_truth resource_id must match the injected resource_id")
        return self


def parse_scenario(raw: dict[str, Any]) -> ScenarioDefinition:
    return ScenarioDefinition.model_validate(raw)


def load_scenario(path: Path) -> ScenarioDefinition:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: scenario file must be a mapping")
    return parse_scenario(raw)


def load_scenarios(directory: Path) -> dict[str, ScenarioDefinition]:
    scenarios = [load_scenario(path) for path in sorted(directory.glob("*.yaml"))]
    return {scenario.name: scenario for scenario in scenarios}
