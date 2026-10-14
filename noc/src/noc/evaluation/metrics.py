import csv
import io
import statistics
from collections import defaultdict
from dataclasses import dataclass

from noc.evaluation.store import DONE, INVALID, RunRecord

CSV_COLUMNS = (
    "variant",
    "scenario",
    "runs",
    "invalid",
    "detection_rate",
    "root_cause_accuracy",
    "outcome_accuracy",
    "median_detection_seconds",
)


@dataclass(frozen=True)
class CellSummary:
    variant: str
    scenario: str
    runs: int
    invalid: int
    detection_rate: float | None
    root_cause_accuracy: float | None
    outcome_accuracy: float | None
    median_detection_seconds: float | None


def ratio(hits: int, total: int) -> float | None:
    return None if total == 0 else hits / total


def outcome_matches(record: RunRecord) -> bool:
    return (
        record.expected_outcome is not None
        and record.final_status is not None
        and (record.final_status.lower() == record.expected_outcome.lower())
    )


def summarize(records: list[RunRecord], variant: str, scenario: str) -> CellSummary:
    done = [record for record in records if record.status == DONE]
    detected = [record for record in done if record.detected]
    scored = [record for record in detected if record.root_cause_match is not None]
    seconds = [
        record.detection_seconds for record in detected if record.detection_seconds is not None
    ]
    return CellSummary(
        variant=variant,
        scenario=scenario,
        runs=len(done),
        invalid=sum(1 for record in records if record.status == INVALID),
        detection_rate=ratio(len(detected), len(done)),
        root_cause_accuracy=ratio(sum(1 for r in scored if r.root_cause_match), len(done)),
        outcome_accuracy=ratio(sum(1 for r in detected if outcome_matches(r)), len(done)),
        median_detection_seconds=statistics.median(seconds) if seconds else None,
    )


def summarize_all(records: list[RunRecord]) -> list[CellSummary]:
    cells: dict[tuple[str, str], list[RunRecord]] = defaultdict(list)
    for record in records:
        cells[(record.variant, record.scenario)].append(record)
    return [summarize(cells[key], variant=key[0], scenario=key[1]) for key in sorted(cells)]


def to_csv(summaries: list[CellSummary]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for summary in summaries:
        writer.writerow(
            [
                summary.variant,
                summary.scenario,
                summary.runs,
                summary.invalid,
                *(
                    "" if value is None else f"{value:.4f}"
                    for value in (
                        summary.detection_rate,
                        summary.root_cause_accuracy,
                        summary.outcome_accuracy,
                        summary.median_detection_seconds,
                    )
                ),
            ]
        )
    return buffer.getvalue()
