from dataclasses import dataclass
from typing import Final, cast

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.db.base import utc_now
from noc.db.models import NocSetting
from noc.llm.providers import TIERS, ProvidersDocument, parse_chain_entry
from noc.llm.types import Tier

logger = structlog.get_logger(__name__)

CHAIN_SETTING_PREFIX: Final = "llm.chain."
MAX_CHAIN_LENGTH: Final = 8


class ChainRefused(ValueError):
    pass


@dataclass(frozen=True)
class ChainOption:
    provider: str
    model_tier: Tier
    model: str

    @property
    def entry(self) -> str:
        return f"{self.provider}:{self.model_tier}"


def chain_setting_key(tier: str) -> str:
    return f"{CHAIN_SETTING_PREFIX}{tier}"


def chain_options(document: ProvidersDocument) -> list[ChainOption]:
    return [
        ChainOption(name, model_tier, limits.model)
        for name, config in document.providers.items()
        for model_tier, limits in config.models.items()
    ]


def default_chains(document: ProvidersDocument) -> dict[Tier, list[str]]:
    chains: dict[Tier, list[str]] = {}
    for tier, names in document.chains.items():
        parsed = [parse_chain_entry(name, tier) for name in names]
        chains[tier] = [f"{entry.provider}:{entry.model_tier}" for entry in parsed]
    return chains


def validate_chain(document: ProvidersDocument, entries: list[str]) -> list[str]:
    if not entries:
        raise ChainRefused("the order needs at least one model")
    if len(entries) > MAX_CHAIN_LENGTH:
        raise ChainRefused(f"the order can name at most {MAX_CHAIN_LENGTH} models")
    known = {option.entry for option in chain_options(document)}
    cleaned: list[str] = []
    for raw in entries:
        entry = raw.strip()
        if entry not in known:
            raise ChainRefused(
                f"{entry or 'an empty entry'} is not a model listed in providers.yaml"
            )
        if entry in cleaned:
            raise ChainRefused(f"{entry} is listed more than once")
        cleaned.append(entry)
    return cleaned


async def chain_overrides(
    session: AsyncSession, document: ProvidersDocument
) -> dict[Tier, list[str]]:
    rows = await session.scalars(
        select(NocSetting).where(NocSetting.key.startswith(CHAIN_SETTING_PREFIX))
    )
    overrides: dict[Tier, list[str]] = {}
    for row in rows:
        tier = row.key.removeprefix(CHAIN_SETTING_PREFIX)
        if tier not in TIERS:
            continue
        stored = row.value.get("entries", []) if isinstance(row.value, dict) else []
        try:
            overrides[cast(Tier, tier)] = validate_chain(document, [str(item) for item in stored])
        except ChainRefused:
            logger.warning("llm_chain_override_ignored", tier=tier)
    return overrides


def effective_chains(
    document: ProvidersDocument, overrides: dict[Tier, list[str]]
) -> dict[Tier, list[str]]:
    chains = default_chains(document)
    chains.update(overrides)
    return chains


def check_tier(tier: str) -> Tier:
    if tier not in TIERS:
        raise ChainRefused(f"unknown tier {tier}")
    return cast(Tier, tier)


async def set_chain(
    session: AsyncSession,
    document: ProvidersDocument,
    tier: str,
    entries: list[str],
    actor: str,
) -> list[str]:
    checked = check_tier(tier)
    cleaned = validate_chain(document, entries)
    key = chain_setting_key(checked)
    setting = await session.get(NocSetting, key)
    value = {"entries": cleaned}
    if setting is None:
        session.add(NocSetting(key=key, value=value, updated_by=actor))
    else:
        setting.value = value
        setting.updated_at = utc_now()
        setting.updated_by = actor
    await session.flush()
    await append_audit(
        session, actor, "llm_chain_set", f"llm:chain:{checked}", {"entries": cleaned}
    )
    return cleaned


async def reset_chain(session: AsyncSession, tier: str, actor: str) -> None:
    checked = check_tier(tier)
    setting = await session.get(NocSetting, chain_setting_key(checked))
    if setting is not None:
        await session.delete(setting)
        await session.flush()
    await append_audit(session, actor, "llm_chain_reset", f"llm:chain:{checked}", {})
