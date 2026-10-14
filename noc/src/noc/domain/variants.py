from dataclasses import dataclass
from typing import Final, Literal

Variant = Literal["single", "multi", "multi-strong", "runbook"]

VARIANTS: Final[tuple[Variant, ...]] = ("single", "multi", "multi-strong", "runbook")
PLAN_NAMES: Final[dict[str, Variant]] = {
    "sa": "single",
    "ma": "multi",
    "ma-strong": "multi-strong",
    "rb": "runbook",
}


@dataclass(frozen=True)
class ModePolicy:
    default: Variant = "single"
    honour_override: bool = False


def parse_variant(value: str | None) -> Variant | None:
    for variant in VARIANTS:
        if value == variant:
            return variant
    return None


def variant_for_plan_name(name: str) -> Variant:
    return PLAN_NAMES[name]


def mode_for_new_incident(policy: ModePolicy, override: str | None) -> Variant:
    chosen = parse_variant(override) if policy.honour_override else None
    return chosen or policy.default
