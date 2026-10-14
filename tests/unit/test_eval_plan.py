from collections import Counter, defaultdict
from pathlib import Path

import pytest
from pydantic import ValidationError

from noc.evaluation.plan import EvalPlan, PlannedRun, build_schedule, load_plan


def make_plan(**changes: object) -> EvalPlan:
    values: dict[str, object] = {
        "name": "pilot",
        "scenarios": ["service-down", "cpu-burn"],
        "variants": ["ma", "ma-strong", "sa", "rb"],
        "repetitions": 3,
        "seed": 11,
    }
    values.update(changes)
    return EvalPlan.model_validate(values)


def cells_of(runs: list[PlannedRun]) -> set[tuple[str, str, int]]:
    return {(run.scenario, run.variant, run.repetition) for run in runs}


def test_schedule_has_one_run_per_scenario_variant_and_repetition() -> None:
    schedule = build_schedule(make_plan())
    cells = Counter((run.scenario, run.variant, run.repetition) for run in schedule)
    assert len(schedule) == 2 * 4 * 3
    assert set(cells.values()) == {1}


def test_positions_are_a_gapless_sequence() -> None:
    schedule = build_schedule(make_plan())
    assert [run.position for run in schedule] == list(range(len(schedule)))


def test_all_variants_of_a_block_share_one_seed() -> None:
    seeds: dict[tuple[str, int], set[int]] = defaultdict(set)
    for run in build_schedule(make_plan()):
        seeds[(run.scenario, run.repetition)].add(run.seed)
    assert all(len(values) == 1 for values in seeds.values())
    assert len({next(iter(values)) for values in seeds.values()}) == len(seeds)


def test_schedule_is_deterministic_for_one_plan() -> None:
    assert build_schedule(make_plan()) == build_schedule(make_plan())


def test_another_seed_changes_the_order_but_not_the_cells() -> None:
    first = build_schedule(make_plan(seed=1))
    second = build_schedule(make_plan(seed=2))
    assert cells_of(first) == cells_of(second)
    assert [(r.scenario, r.variant) for r in first] != [(r.scenario, r.variant) for r in second]


def test_variants_are_interleaved_not_run_in_one_long_batch() -> None:
    order = [run.variant for run in build_schedule(make_plan(repetitions=6))]
    assert len(set(order[:4])) == 4
    assert order != sorted(order)


def test_duplicate_variants_are_refused() -> None:
    with pytest.raises(ValidationError):
        make_plan(variants=["ma", "ma"])


def test_unknown_variant_is_refused() -> None:
    with pytest.raises(ValidationError):
        make_plan(variants=["ma", "gpt"])


def test_load_plan_reads_yaml(tmp_path: Path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text(
        "name: main\nscenarios: [service-down]\nvariants: [ma, rb]\nrepetitions: 8\nseed: 5\n",
        encoding="utf-8",
    )
    assert load_plan(path).repetitions == 8


def test_load_plan_refuses_a_list(tmp_path: Path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text("- a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_plan(path)
