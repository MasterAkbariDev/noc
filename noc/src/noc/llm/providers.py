import hashlib
import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from noc.llm.types import Tier


class ModelLimits(BaseModel):
    model: str
    rpm: int = Field(gt=0)
    rpd: int = Field(gt=0)


KEY_SEPARATORS = re.compile(r"[\s,;\"']+")


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str
    api_keys_env: str | None = None
    proxy_env: str | None = None
    quota_timezone: str = "UTC"
    models: dict[Tier, ModelLimits]

    def api_keys(self) -> list[str]:
        variables = [self.api_keys_env, self.api_key_env]
        raw = " ".join(os.environ.get(name, "") for name in variables if name)
        keys = [key for key in KEY_SEPARATORS.split(raw) if key]
        return list(dict.fromkeys(keys))

    def proxy_url(self) -> str | None:
        if self.proxy_env is None:
            return None
        return os.environ.get(self.proxy_env, "").strip() or None


def key_label(provider: str, key: str) -> str:
    return f"{provider}#{hashlib.sha256(key.encode()).hexdigest()[:8]}"


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
