import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast, get_args

import yaml
from pydantic import BaseModel, Field

from noc.llm.types import Tier


class ModelLimits(BaseModel):
    model: str
    rpm: int = Field(gt=0)
    rpd: int = Field(gt=0)


TIERS: tuple[str, ...] = get_args(Tier)
KeyTier = Literal["free", "paid"]
KEY_TIERS: tuple[str, ...] = get_args(KeyTier)
KEY_SEPARATORS = re.compile(r"[\s,;\"']+")


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str
    api_keys_env: str | None = None
    proxy_env: str | None = None
    quota_timezone: str = "UTC"
    foreign_tool_call_extra: dict[str, Any] = Field(default_factory=dict)
    models: dict[Tier, ModelLimits]
    paid_models: dict[Tier, ModelLimits] = Field(default_factory=dict)

    def limits_for(self, model_tier: Tier, key_tier: KeyTier) -> ModelLimits | None:
        if key_tier == "paid" and model_tier in self.paid_models:
            return self.paid_models[model_tier]
        return self.models.get(model_tier)

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


@dataclass(frozen=True)
class ChainEntry:
    provider: str
    model_tier: Tier


def parse_chain_entry(entry: str, tier: Tier) -> ChainEntry:
    provider, _, model_tier = entry.partition(":")
    if model_tier and model_tier not in TIERS:
        raise ValueError(f"chain {tier} entry {entry!r} names an unknown tier")
    return ChainEntry(provider, cast(Tier, model_tier or tier))


def load_providers(path: Path) -> ProvidersDocument:
    document = ProvidersDocument.model_validate(yaml.safe_load(path.read_text()))
    for tier, chain in document.chains.items():
        entries = [parse_chain_entry(entry, tier) for entry in chain]
        missing = [entry.provider for entry in entries if entry.provider not in document.providers]
        if missing:
            raise ValueError(f"chain {tier} references unknown providers {missing}")
    return document
