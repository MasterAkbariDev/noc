from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Specialist = Literal["metrics", "logs", "network", "security"]

SPECIALISTS: tuple[Specialist, ...] = ("metrics", "logs", "network", "security")


class AlertRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    specialists: list[Specialist] = Field(min_length=1)
    focus: dict[Specialist, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def focus_targets_are_base_specialists(self) -> "AlertRoute":
        stray = [name for name in self.focus if name not in self.specialists]
        if stray:
            raise ValueError(f"focus names specialists not in the base set: {stray}")
        return self


class RoutingTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alerts: dict[str, AlertRoute]


class InvestigationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    specialists: list[Specialist]
    focus: dict[Specialist, list[str]]
    not_selected: list[Specialist]


def load_routing(path: Path) -> RoutingTable:
    return RoutingTable.model_validate(yaml.safe_load(path.read_text()))


def plan_investigation(alertnames: list[str], routing: RoutingTable) -> InvestigationPlan:
    selected: set[Specialist] = set()
    focus: dict[Specialist, list[str]] = {}
    for name in alertnames:
        route = routing.alerts.get(name)
        if route is None:
            selected.update(SPECIALISTS)
            continue
        selected.update(route.specialists)
        for specialist, questions in route.focus.items():
            bucket = focus.setdefault(specialist, [])
            for question in questions:
                if question not in bucket:
                    bucket.append(question)
    if not alertnames:
        selected.update(SPECIALISTS)
    ordered = [specialist for specialist in SPECIALISTS if specialist in selected]
    return InvestigationPlan(
        specialists=ordered,
        focus={specialist: focus[specialist] for specialist in ordered if specialist in focus},
        not_selected=[specialist for specialist in SPECIALISTS if specialist not in selected],
    )
