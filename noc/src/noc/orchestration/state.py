from typing import Literal, TypedDict

Outcome = Literal["self_resolved", "escalated", "diagnosed"]


class IncidentState(TypedDict):
    incident_id: str
    outcome: Outcome | None
