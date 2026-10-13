from typing import Literal, NotRequired, TypedDict

from noc.agents.supervisor import Specialist

Outcome = Literal["self_resolved", "escalated", "diagnosed"]


class IncidentState(TypedDict):
    incident_id: str
    outcome: Outcome | None
    specialists: NotRequired[list[Specialist]]
    focus: NotRequired[dict[Specialist, list[str]]]


class SpecialistTask(TypedDict):
    incident_id: str
    specialist: Specialist
    focus: list[str]
