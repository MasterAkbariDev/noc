import pytest

from noc.domain.variants import (
    PLAN_NAMES,
    VARIANTS,
    ModePolicy,
    mode_for_new_incident,
    parse_variant,
    variant_for_plan_name,
)
from noc.evaluation.plan import EvalPlan


def test_plan_names_cover_every_variant_exactly_once() -> None:
    assert sorted(PLAN_NAMES.values()) == sorted(VARIANTS)


def test_every_plan_variant_literal_has_a_mapping() -> None:
    plan = EvalPlan(
        name="p", scenarios=["service-down"], variants=list(PLAN_NAMES), repetitions=1, seed=1
    )
    assert {variant_for_plan_name(name) for name in plan.variants} == set(VARIANTS)


@pytest.mark.parametrize("variant", VARIANTS)
def test_known_variants_parse(variant: str) -> None:
    assert parse_variant(variant) == variant


@pytest.mark.parametrize("value", [None, "", "gpt", "MULTI", "multi "])
def test_unknown_variants_do_not_parse(value: str | None) -> None:
    assert parse_variant(value) is None


def test_default_applies_without_override() -> None:
    assert mode_for_new_incident(ModePolicy(default="multi"), None) == "multi"


def test_override_is_ignored_unless_eval_mode_honours_it() -> None:
    policy = ModePolicy(default="single", honour_override=False)
    assert mode_for_new_incident(policy, "runbook") == "single"


def test_override_wins_when_honoured() -> None:
    policy = ModePolicy(default="single", honour_override=True)
    assert mode_for_new_incident(policy, "runbook") == "runbook"


def test_an_unknown_override_falls_back_to_the_default() -> None:
    policy = ModePolicy(default="multi", honour_override=True)
    assert mode_for_new_incident(policy, "nonsense") == "multi"
