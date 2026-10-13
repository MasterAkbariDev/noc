from dataclasses import dataclass, field

from noc.detection.alerts import PrometheusAlert


@dataclass(frozen=True)
class OpenAlertState:
    fingerprint: str
    missed_polls: int


@dataclass
class ReconcilePlan:
    new: list[PrometheusAlert] = field(default_factory=list)
    still_firing: list[PrometheusAlert] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)


def plan_reconciliation(
    open_alerts: list[OpenAlertState],
    firing: list[PrometheusAlert],
    missing_polls_to_resolve: int,
) -> ReconcilePlan:
    plan = ReconcilePlan()
    known = {state.fingerprint: state for state in open_alerts}
    firing_by_fingerprint = {alert.fingerprint: alert for alert in firing}

    for fingerprint, alert in firing_by_fingerprint.items():
        if fingerprint in known:
            plan.still_firing.append(alert)
        else:
            plan.new.append(alert)

    for fingerprint, state in known.items():
        if fingerprint in firing_by_fingerprint:
            continue
        if state.missed_polls + 1 >= missing_polls_to_resolve:
            plan.resolved.append(fingerprint)
        else:
            plan.missed.append(fingerprint)

    return plan
