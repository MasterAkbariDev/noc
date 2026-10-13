import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from noc.llm.types import Tier


class ModelLimits(BaseModel):
    model: str
    rpm: int = Field(gt=0)
    rpd: int = Field(gt=0)


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str
    quota_timezone: str = "UTC"
    models: dict[Tier, ModelLimits]

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


class ProvidersDocument(BaseModel):
    providers: dict[str, ProviderConfig]
    chains: dict[Tier, list[str]]


def load_providers(path: Path) -> ProvidersDocument:
    document = ProvidersDocument.model_validate(yaml.safe_load(path.read_text()))
    for tier, chain in document.chains.items():
        missing = [name for name in chain if name not in document.providers]
        if missing:
            raise ValueError(f"chain {tier} references unknown providers {missing}")
    return document
