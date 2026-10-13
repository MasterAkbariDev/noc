from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, model_validator

from noc_shared.resources import ManagedResource, ResourceKind

SENTINEL_VERSION = "0.1.0"
CHAOS_TTL_CEILING_SECONDS = 900


class TlsConfig(BaseModel):
    cert_file: Path
    key_file: Path
    client_ca_file: Path


class ListenConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 9443


class ChaosConfig(BaseModel):
    enabled: bool = False
    key_id: str | None = None
    key_file: Path | None = None
    max_ttl_seconds: int = Field(CHAOS_TTL_CEILING_SECONDS, ge=1, le=CHAOS_TTL_CEILING_SECONDS)


class SentinelConfig(BaseModel):
    target: str
    environment: str = Field(pattern="^(lab|prod)$")
    listen: ListenConfig = ListenConfig()
    tls: TlsConfig | None = None
    key_files: dict[str, Path]
    chaos: ChaosConfig = ChaosConfig()
    state_dir: Path = Path("/var/lib/noc-sentinel")
    halt_file: Path = Path("/etc/noc-sentinel/HALT")
    max_skew_seconds: int = 30
    nonce_ttl_seconds: int = 300
    resources: list[ManagedResource] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_chaos_key(self) -> Self:
        if self.chaos.enabled and (self.chaos.key_id is None or self.chaos.key_file is None):
            raise ValueError("chaos.enabled requires chaos.key_id and chaos.key_file")
        if self.chaos.key_id is not None and self.chaos.key_id in self.key_files:
            raise ValueError("chaos.key_id must not also appear in key_files")
        return self

    def resource(self, resource_id: str) -> ManagedResource | None:
        return next((r for r in self.resources if r.id == resource_id), None)

    def resources_of_kind(self, kind: ResourceKind) -> list[ManagedResource]:
        return [r for r in self.resources if r.kind == kind]

    def load_secrets(self) -> dict[str, bytes]:
        return {key_id: path.read_bytes().strip() for key_id, path in self.key_files.items()}

    def load_chaos_secrets(self) -> dict[str, bytes]:
        if self.chaos.key_id is None or self.chaos.key_file is None:
            raise ValueError("chaos key is not configured")
        return {self.chaos.key_id: self.chaos.key_file.read_bytes().strip()}


def load_config(path: Path) -> SentinelConfig:
    raw = yaml.safe_load(path.read_text())
    return SentinelConfig.model_validate(raw)
