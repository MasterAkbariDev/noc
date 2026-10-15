from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

from noc_shared.taxonomy import RootCauseCode

GUIDE_PATH: Final = Path(__file__).with_name("operator_guide.yaml")
UNIT_PLACEHOLDER: Final = "<service>"
MOUNT_PLACEHOLDER: Final = "/"


class GuideStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    command: str | None = None


class OperatorGuide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_causes: dict[RootCauseCode, list[GuideStep]]
    alerts: dict[str, list[GuideStep]]
    fallback: list[GuideStep] = Field(min_length=1)
    after_fix: dict[RootCauseCode, list[GuideStep]]


@dataclass(frozen=True)
class GuideContext:
    unit: str | None = None
    mount: str | None = None


@cache
def load_guide(path: Path = GUIDE_PATH) -> OperatorGuide:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return OperatorGuide.model_validate(raw)


def filled(step: GuideStep, context: GuideContext) -> GuideStep:
    if step.command is None:
        return step
    command = step.command.replace("{unit}", context.unit or UNIT_PLACEHOLDER)
    command = command.replace("{mount}", context.mount or MOUNT_PLACEHOLDER)
    return step.model_copy(update={"command": command})


def steps_to_fix(
    guide: OperatorGuide, code: str | None, alertname: str | None, context: GuideContext
) -> list[GuideStep]:
    steps = guide.fallback
    if alertname in guide.alerts:
        steps = guide.alerts[alertname]
    if code is not None and code != RootCauseCode.UNKNOWN and code in guide.root_causes:
        steps = guide.root_causes[RootCauseCode(code)]
    return [filled(step, context) for step in steps]


def steps_after_fix(
    guide: OperatorGuide, code: str | None, context: GuideContext
) -> list[GuideStep]:
    if code is None or code not in guide.after_fix:
        return []
    return [filled(step, context) for step in guide.after_fix[RootCauseCode(code)]]
