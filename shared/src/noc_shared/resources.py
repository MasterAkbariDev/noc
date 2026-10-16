from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

RESOURCE_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,30}:[A-Za-z0-9@._-]{1,128}$"

ResourceId = Annotated[str, StringConstraints(pattern=RESOURCE_ID_PATTERN)]


class ResourceKind(StrEnum):
    SYSTEMD_UNIT = "systemd_unit"
    BATCH_UNIT = "batch_unit"
    DIRECTORY = "directory"
    DOCKER_ENGINE = "docker_engine"
    CONTAINER = "container"
    LOG_SOURCE = "log_source"
    PG_INSTANCE = "pg_instance"
    HTTP_ENDPOINT = "http_endpoint"


class ManagedResource(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ResourceId
    kind: ResourceKind
    name: str = Field(min_length=1, max_length=128)
    allowed_actions: tuple[str, ...] = ()


class Inventory(BaseModel):
    target: str
    environment: str
    sentinel_version: str
    halted: bool
    resources: list[ManagedResource]
