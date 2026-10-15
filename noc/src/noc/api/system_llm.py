from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, get_settings_dep, require_role
from noc.api.schemas import LlmKeyView, LlmModelUsage, LlmStatus
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.models import LlmKeyStatus, LlmQuotaUsage
from noc.llm.keys import KeyEntry, all_keys
from noc.llm.providers import (
    KeyTier,
    ModelLimits,
    ProviderConfig,
    ProvidersDocument,
    load_providers,
)
from noc.secret_store import SecretStore

router = APIRouter(
    prefix="/api/system", tags=["system"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
UsageKey = tuple[str, str, date]


@dataclass(frozen=True)
class KeySlot:
    label: str
    provider: str
    config: ProviderConfig | None
    status: LlmKeyStatus | None
    tier: KeyTier = "free"


@dataclass(frozen=True)
class ModelSlot:
    tier: str
    limits: ModelLimits
    day: date


@router.get("/llm")
async def get_llm_status(session: Session, settings: AppSettings) -> LlmStatus:
    document = load_providers(settings.llm_providers_file)
    statuses = list(await session.scalars(select(LlmKeyStatus).order_by(LlmKeyStatus.label)))
    entries = await all_keys(session, SecretStore(settings.secrets_dir), document)
    keys = key_slots(document, statuses, entries)
    usage = await used_today(session, keys)
    return LlmStatus(mode=settings.llm_mode, keys=[key_view(key, usage) for key in keys])


def key_slots(
    document: ProvidersDocument, statuses: list[LlmKeyStatus], entries: list[KeyEntry]
) -> list[KeySlot]:
    status_by_label = {status.label: status for status in statuses}
    slots = [
        KeySlot(
            entry.label,
            entry.provider,
            document.providers.get(entry.provider),
            status_by_label.get(entry.label),
            entry.tier,
        )
        for entry in entries
    ]
    configured = {slot.label for slot in slots}
    for status in statuses:
        if status.label not in configured:
            stored_config = document.providers.get(status.provider)
            slots.append(KeySlot(status.label, status.provider, stored_config, status))
    return slots


def model_slots(key: KeySlot) -> list[ModelSlot]:
    if key.config is None:
        return []
    day = quota_day(key.config.quota_timezone)
    slots: list[ModelSlot] = []
    for tier in key.config.models:
        limits = key.config.limits_for(tier, key.tier)
        if limits is not None:
            slots.append(ModelSlot(tier, limits, day))
    return slots


def quota_day(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


async def used_today(session: AsyncSession, keys: list[KeySlot]) -> dict[UsageKey, int]:
    wanted = [(key.label, slot.limits.model, slot.day) for key in keys for slot in model_slots(key)]
    if not wanted:
        return {}
    rows = await session.scalars(
        select(LlmQuotaUsage).where(
            LlmQuotaUsage.provider.in_({label for label, _, _ in wanted}),
            LlmQuotaUsage.day.in_({day for _, _, day in wanted}),
        )
    )
    return {(row.provider, row.model, row.day): row.requests for row in rows}


def key_view(key: KeySlot, usage: dict[UsageKey, int]) -> LlmKeyView:
    status = key.status
    return LlmKeyView(
        label=key.label,
        provider=key.provider,
        tier=key.tier,
        state=status.state if status else "unused",
        cooling_until=status.cooling_until if status else None,
        last_error=status.last_error if status else None,
        last_error_at=status.last_error_at if status else None,
        last_success_at=status.last_success_at if status else None,
        models=[
            LlmModelUsage(
                tier=slot.tier,
                model=slot.limits.model,
                used_today=usage.get((key.label, slot.limits.model, slot.day), 0),
                daily_limit=slot.limits.rpd,
            )
            for slot in model_slots(key)
        ],
    )
