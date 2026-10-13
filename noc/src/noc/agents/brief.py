import json
from datetime import datetime

from pydantic import BaseModel


class AlertBrief(BaseModel):
    alertname: str
    severity: str
    resource: str | None
    value: str | None
    firing_since: datetime
    summary: str | None


class ResourceBrief(BaseModel):
    id: str
    kind: str
    name: str


class IncidentBrief(BaseModel):
    title: str
    target: str
    environment: str
    alerts: list[AlertBrief]
    resources: list[ResourceBrief]


def render_brief(brief: IncidentBrief) -> str:
    body = json.dumps(brief.model_dump(mode="json"), indent=1, sort_keys=True)
    return f'<incident_brief source="noc">\n{body}\n</incident_brief>'
