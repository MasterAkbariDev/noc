import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

SCENARIO_NAME_PATTERN: Final = r"^[a-z0-9][a-z0-9-]*$"
PLAN_NAME_PATTERN: Final = r"^[a-z0-9][a-z0-9_-]*$"
SEED_MODULUS: Final = 2**31

Variant = Literal["ma", "ma-strong", "sa", "rb"]


class EvalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=PLAN_NAME_PATTERN, max_length=64)
    scenarios: list[str] = Field(min_length=1)
    variants: list[Variant] = Field(min_length=1)
    repetitions: int = Field(ge=1, le=50)
    seed: int = Field(ge=0, lt=SEED_MODULUS)

    @field_validator("scenarios")
    @classmethod
    def scenarios_are_unique_names(cls, scenarios: list[str]) -> list[str]:
        if len(set(scenarios)) != len(scenarios):
            raise ValueError("scenarios must not repeat")
        return scenarios

    @field_validator("variants")
    @classmethod
    def variants_are_unique(cls, variants: list[Variant]) -> list[Variant]:
        if len(set(variants)) != len(variants):
            raise ValueError("variants must not repeat")
        return variants


@dataclass(frozen=True)
class PlannedRun:
    position: int
    scenario: str
    variant: str
    repetition: int
    seed: int


def load_plan(path: Path) -> EvalPlan:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: an evaluation plan must be a mapping")
    return EvalPlan.model_validate(raw)


def seed_for(plan: EvalPlan, scenario: str, repetition: int) -> int:
    digest = hashlib.sha256(f"{plan.seed}:{scenario}:{repetition}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % SEED_MODULUS


def build_schedule(plan: EvalPlan) -> list[PlannedRun]:
    blocks = [
        (scenario, repetition)
        for repetition in range(1, plan.repetitions + 1)
        for scenario in plan.scenarios
    ]
    random.Random(plan.seed).shuffle(blocks)
    runs: list[PlannedRun] = []
    for scenario, repetition in blocks:
        seed = seed_for(plan, scenario, repetition)
        variants = list(plan.variants)
        random.Random(f"{plan.seed}:{scenario}:{repetition}").shuffle(variants)
        for variant in variants:
            runs.append(PlannedRun(len(runs), scenario, variant, repetition, seed))
    return runs
