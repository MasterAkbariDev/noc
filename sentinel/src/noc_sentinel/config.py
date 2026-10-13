from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from noc_shared.resources import ManagedResource, ResourceKind

SENTINEL_VERSION = "0.1.0"


class TlsConfig(BaseModel):
    cert_file: Path
    key_file: Path
    client_ca_file: Path


class ListenConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 9443


class SentinelConfig(BaseModel):
    target: str
    environment: str = Field(pattern="^(lab|prod)$")
    listen: ListenConfig = ListenConfig()
    tls: TlsConfig | None = None
    key_files: dict[str, Path]
    state_dir: Path = Path("/var/lib/noc-sentinel")
    halt_file: Path = Path("/etc/noc-sentinel/HALT")
    max_skew_seconds: int = 30
    nonce_ttl_seconds: int = 300
    resources: list[ManagedResource] = Field(default_factory=list)

    def resource(self, resource_id: str) -> ManagedResource | None:
        return next((r for r in self.resources if r.id == resource_id), None)

    def resources_of_kind(self, kind: ResourceKind) -> list[ManagedResource]:
        return [r for r in self.resources if r.kind == kind]

    def load_secrets(self) -> dict[str, bytes]:
        return {key_id: path.read_bytes().strip() for key_id, path in self.key_files.items()}


def load_config(path: Path) -> SentinelConfig:
    raw = yaml.safe_load(path.read_text())
    return SentinelConfig.model_validate(raw)
