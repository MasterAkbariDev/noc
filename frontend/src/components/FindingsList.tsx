import type { FindingView } from "../api/types";
import { formatConfidence } from "./format";

export function findingAnchor(label: string): string {
  return `finding-${label.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

function groupByAgent(findings: FindingView[]): [string, FindingView[]][] {
  const groups = new Map<string, FindingView[]>();
  for (const finding of findings) {
    groups.set(finding.agent, [...(groups.get(finding.agent) ?? []), finding]);
  }
  return [...groups.entries()];
}

function FindingItem({ finding }: { finding: FindingView }) {
  return (
    <li id={findingAnchor(finding.label)} className="card">
      <div className="finding-head">
        <strong>{finding.label}</strong>
        <span className="muted">
          {finding.category} / {finding.severity} / confidence {formatConfidence(finding.confidence)}
        </span>
        <span className="badge">{finding.evidence_strength}</span>
        {finding.grounded ? (
          <span className="badge badge-ok">grounded</span>
        ) : (
          <span className="badge badge-warn">ungrounded</span>
        )}
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
      {finding.counter_evidence.length > 0 && (
        <div>
          <div className="muted">Counter-evidence</div>
          <ul className="evidence">
            {finding.counter_evidence.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

export function FindingsList({ findings }: { findings: FindingView[] }) {
  if (findings.length === 0) {
    return <p className="muted">No findings recorded.</p>;
  }
  return (
    <div className="finding-groups">
      {groupByAgent(findings).map(([agent, items]) => (
        <div key={agent} className="finding-group">
          <h3 className="subhead">{agent}</h3>
          <ul className="findings">
            {items.map((finding) => (
              <FindingItem key={finding.label} finding={finding} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
