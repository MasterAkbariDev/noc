import json
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict

from noc.agents.schemas import FindingCategory
from noc_shared.taxonomy import RootCauseCode

RUNBOOK_FILE: Final = Path(__file__).parent / "runbook.yaml"
LABEL_PREFIX: Final = "$"
OK_MARKER: Final = 'ok="true"'


class RunbookEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause: RootCauseCode
    tool: str
    args: dict[str, str]
    category: FindingCategory
    excerpt_key: str | None = None


class Runbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alerts: dict[str, RunbookEntry]


def load_runbook(path: Path = RUNBOOK_FILE) -> Runbook:
    return Runbook.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def entry_for(runbook: Runbook, alertnames: list[str]) -> tuple[str, RunbookEntry] | None:
    for alertname in alertnames:
        entry = runbook.alerts.get(alertname)
        if entry is not None:
            return alertname, entry
    return None


def resolve_arguments(entry: RunbookEntry, labels: dict[str, str]) -> dict[str, str] | None:
    resolved: dict[str, str] = {}
    for name, value in entry.args.items():
        if not value.startswith(LABEL_PREFIX):
            resolved[name] = value
            continue
        label = labels.get(value[len(LABEL_PREFIX) :])
        if not label:
            return None
        resolved[name] = label
    return resolved


def excerpt_for(entry: RunbookEntry, data: dict[str, Any] | None) -> str:
    if entry.excerpt_key is None or data is None or entry.excerpt_key not in data:
        return OK_MARKER
    return f"{json.dumps(entry.excerpt_key)}: {json.dumps(data[entry.excerpt_key])}"
