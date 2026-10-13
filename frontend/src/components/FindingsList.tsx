import type { FindingView } from "../api/types";
import { formatConfidence } from "./format";

export function FindingsList({ findings }: { findings: FindingView[] }) {
  if (findings.length === 0) {
    return <p className="muted">No findings recorded.</p>;
  }
  return (
    <ul className="findings">
      {findings.map((finding) => (
        <li key={finding.label} className="card">
          <div className="finding-head">
            <strong>{finding.label}</strong>
            <span className="muted">
              {finding.agent} / {finding.category} / {finding.severity} / confidence{" "}
              {formatConfidence(finding.confidence)}
            </span>
            {finding.suspected_injection && <span className="badge badge-warn">suspected injection</span>}
          </div>
          <p>{finding.summary}</p>
          {finding.evidence.length > 0 && (
            <div>
              <div className="muted">Evidence</div>
              <ul className="evidence">
                {finding.evidence.map((item, index) => (
                  <li key={index}>
                    <code>{JSON.stringify(item)}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
