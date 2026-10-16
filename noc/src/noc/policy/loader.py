from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from noc.policy.models import ActionDefinition, ScoreWeights


class PolicyDocument(BaseModel):
    version: str
    weights: ScoreWeights
    protected_resources: frozenset[str] = frozenset()
    max_actions_per_incident: int = Field(2, ge=1, le=3)
    actions: dict[str, ActionDefinition]
    root_cause_actions: dict[str, list[str]] = Field(default_factory=dict)

    def candidate_actions(self, root_cause_code: str) -> list[str]:
        return [a for a in self.root_cause_actions.get(root_cause_code, []) if a in self.actions]


def load_policy(path: Path) -> PolicyDocument:
    raw = yaml.safe_load(path.read_text())
    for name, definition in raw.get("actions", {}).items():
        definition["name"] = name
    document = PolicyDocument.model_validate(raw)
    unknown = {
        action
        for actions in document.root_cause_actions.values()
        for action in actions
        if action not in document.actions
    }
    if unknown:
        raise ValueError(f"root_cause_actions reference unknown actions: {sorted(unknown)}")
    return document
