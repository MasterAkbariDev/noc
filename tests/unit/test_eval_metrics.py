from noc.evaluation.metrics import CSV_COLUMNS, summarize, summarize_all, to_csv
from noc.evaluation.store import DONE, INVALID, RunRecord


def record(
    *,
    variant: str = "ma",
    scenario: str = "service-down",
    status: str = DONE,
    detected: bool | None = True,
    root_cause_match: bool | None = True,
    detection_seconds: float | None = 20.0,
    final_status: str | None = "RESOLVED",
    expected_outcome: str | None = "resolved",
) -> RunRecord:
    return RunRecord(
        scenario=scenario,
        variant=variant,
        repetition=1,
        seed=1,
        status=status,
        attempts=1,
        detected=detected,
        root_cause_match=root_cause_match,
        detection_seconds=detection_seconds,
        final_status=final_status,
        expected_outcome=expected_outcome,
    )


def test_all_correct_runs_score_one() -> None:
    summary = summarize([record(), record()], "ma", "service-down")
    assert summary.runs == 2
    assert summary.detection_rate == 1.0
    assert summary.root_cause_accuracy == 1.0
    assert summary.outcome_accuracy == 1.0
    assert summary.median_detection_seconds == 20.0


def test_wrong_root_cause_lowers_accuracy_but_not_detection() -> None:
    summary = summarize([record(), record(root_cause_match=False)], "ma", "service-down")
    assert summary.detection_rate == 1.0
    assert summary.root_cause_accuracy == 0.5


def test_a_missed_detection_counts_against_every_rate() -> None:
    missed = record(
        detected=False, root_cause_match=None, detection_seconds=None, final_status=None
    )
    summary = summarize([record(), missed], "ma", "service-down")
    assert summary.detection_rate == 0.5
    assert summary.root_cause_accuracy == 0.5
    assert summary.outcome_accuracy == 0.5


def test_invalid_runs_are_counted_and_kept_out_of_the_rates() -> None:
    summary = summarize([record(), record(status=INVALID, root_cause_match=False)], "ma", "x")
    assert summary.runs == 1
    assert summary.invalid == 1
    assert summary.root_cause_accuracy == 1.0


def test_no_finished_runs_gives_no_rates() -> None:
    summary = summarize([record(status="pending")], "ma", "service-down")
    assert summary.runs == 0
    assert summary.detection_rate is None
    assert summary.median_detection_seconds is None


def test_expected_outcome_is_compared_without_case() -> None:
    summary = summarize([record(final_status="ESCALATED", expected_outcome="escalated")], "ma", "x")
    assert summary.outcome_accuracy == 1.0
    wrong = summarize([record(final_status="RESOLVED", expected_outcome="escalated")], "ma", "x")
    assert wrong.outcome_accuracy == 0.0


def test_median_detection_uses_detected_runs_only() -> None:
    runs = [
        record(detection_seconds=10.0),
        record(detection_seconds=30.0),
        record(detection_seconds=50.0),
    ]
    assert summarize(runs, "ma", "x").median_detection_seconds == 30.0


def test_summaries_are_grouped_by_variant_and_scenario() -> None:
    runs = [record(variant="ma"), record(variant="sa"), record(variant="sa", scenario="cpu-burn")]
    cells = [(item.variant, item.scenario) for item in summarize_all(runs)]
    assert cells == [("ma", "service-down"), ("sa", "cpu-burn"), ("sa", "service-down")]


def test_csv_has_header_and_one_row_per_cell() -> None:
    text = to_csv(summarize_all([record(), record(variant="rb", root_cause_match=False)]))
    lines = text.strip().split("\n")
    assert lines[0] == ",".join(CSV_COLUMNS)
    assert lines[1].startswith("ma,service-down,1,0,1.0000,1.0000,1.0000,20.0000")
    assert lines[2].startswith("rb,service-down,1,0,1.0000,0.0000")


def test_csv_leaves_unknown_values_empty() -> None:
    text = to_csv(summarize_all([record(status="pending")]))
    assert text.strip().split("\n")[1] == "ma,service-down,0,0,,,,"
