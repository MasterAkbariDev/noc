import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { getIncident } from "../api/client";
import { CloseIncidentForm } from "../components/CloseIncidentForm";
import { DiagnosisPanel } from "../components/DiagnosisPanel";
import { FindingsList } from "../components/FindingsList";
import { PolicyTable } from "../components/PolicyTable";
import { StatusBadge } from "../components/StatusBadge";
import { Timeline } from "../components/Timeline";
import { errorMessage, formatConfidence, formatTime } from "../components/format";
import { useLivePollInterval } from "../live/useEventStream";

function optionalTime(value: string | null): string {
  return value === null ? "-" : formatTime(value);
}

export function IncidentDetailPage() {
  const { id = "" } = useParams();
  const refetchInterval = useLivePollInterval();

  const query = useQuery({
    queryKey: ["incident", id],
    queryFn: () => getIncident(id),
    enabled: id !== "",
    refetchInterval,
  });

  if (query.isPending) {
    return <p className="muted">Loading incident...</p>;
  }
  if (query.isError) {
    return (
      <section>
        <Link to="/incidents">Back to incidents</Link>
        <p role="alert" className="error">{errorMessage(query.error)}</p>
      </section>
    );
  }

  const incident = query.data;
  return (
    <article>
      <Link to="/incidents">Back to incidents</Link>
      <div className="page-head">
        <h1>{incident.title}</h1>
        <Link to={`/incidents/${incident.id}/trace`}>Agent trace</Link>
      </div>
      <StatusBadge status={incident.status} />

      <section className="card">
        <h2>Summary</h2>
        <dl className="summary">
          <dt>Target</dt>
          <dd>{incident.target}</dd>
          <dt>Mode</dt>
          <dd>{incident.mode}</dd>
          <dt>Severity</dt>
          <dd>{incident.severity}</dd>
          <dt>Opened</dt>
          <dd>{formatTime(incident.opened_at)}</dd>
          <dt>Root cause</dt>
          <dd>
            {incident.root_cause_code ?? "-"} {incident.confidence !== null && formatConfidence(incident.confidence)}
          </dd>
          <dt>Root cause summary</dt>
          <dd>{incident.root_cause_summary ?? "-"}</dd>
          <dt>Escalation reason</dt>
          <dd>{incident.escalation_reason ?? "-"}</dd>
          <dt>Resolution note</dt>
          <dd>{incident.resolution_note ?? "-"}</dd>
          <dt>Trace</dt>
          <dd><code>{incident.trace_id}</code></dd>
        </dl>
      </section>

      <section className="card">
        <h2>Key times</h2>
        <dl className="summary">
          <dt>Investigation started</dt>
          <dd>{optionalTime(incident.investigation_started_at)}</dd>
          <dt>Diagnosed</dt>
          <dd>{optionalTime(incident.diagnosed_at)}</dd>
          <dt>Plan ready</dt>
          <dd>{optionalTime(incident.plan_at)}</dd>
          <dt>Escalated</dt>
          <dd>{optionalTime(incident.escalated_at)}</dd>
          <dt>Resolved</dt>
          <dd>{optionalTime(incident.resolved_at)}</dd>
          <dt>Closed</dt>
          <dd>{optionalTime(incident.closed_at)}</dd>
        </dl>
      </section>

      <CloseIncidentForm incidentId={incident.id} status={incident.status} />

      <section>
        <h2>Timeline</h2>
        <Timeline events={incident.events} />
      </section>

      <section>
        <h2>Diagnosis</h2>
        <DiagnosisPanel diagnosis={incident.diagnosis} />
      </section>

      <section>
        <h2>Findings</h2>
        <FindingsList findings={incident.findings} />
      </section>

      <section>
        <h2>Policy decisions</h2>
        <PolicyTable actions={incident.actions} />
      </section>

      <section>
        <h2>Report</h2>
        {incident.report_markdown === null ? (
          <p className="muted">Report not ready yet.</p>
        ) : (
          <pre className="report">{incident.report_markdown}</pre>
        )}
      </section>
    </article>
  );
}
