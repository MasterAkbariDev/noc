import { Link } from "react-router";
import type { DiagnosisView, HypothesisView } from "../api/types";
import { findingAnchor } from "./FindingsList";
import { formatConfidence } from "./format";

export function DiagnosisPanel({ diagnosis }: { diagnosis: DiagnosisView | null }) {
  if (diagnosis === null) {
    return <p className="muted">Diagnosis not yet recorded.</p>;
  }
  const ranked = [...diagnosis.hypotheses].sort((a, b) => b.confidence - a.confidence);
  return (
    <div className="card">
      <dl className="summary">
        <dt>Primary cause</dt>
        <dd>{diagnosis.primary_code}</dd>
        <dt>Confidence</dt>
        <dd>{formatConfidence(diagnosis.confidence)}</dd>
        <dt>Security incident</dt>
        <dd>{diagnosis.is_security_incident ? "yes" : "no"}</dd>
        <dt>Needs more info</dt>
        <dd>{diagnosis.needs_more_info.join(", ") || "-"}</dd>
        <dt>Ungrounded findings</dt>
        <dd>{diagnosis.ungrounded_findings}</dd>
      </dl>
      <h3 className="subhead">Hypotheses, most likely first</h3>
      {ranked.length === 0 ? (
        <p className="muted">No hypotheses recorded.</p>
      ) : (
        <ol className="hypotheses">
          {ranked.map((hypothesis, index) => (
            <HypothesisItem key={`${hypothesis.root_cause_code}-${index}`} hypothesis={hypothesis} />
          ))}
        </ol>
      )}
    </div>
  );
}

function HypothesisItem({ hypothesis }: { hypothesis: HypothesisView }) {
  return (
    <li className="card hypothesis">
      <div className="finding-head">
        <strong>{hypothesis.root_cause_code}</strong>
        <span className="muted">confidence {formatConfidence(hypothesis.confidence)}</span>
        {hypothesis.affected_resource_id !== null && (
          <span className="muted">resource {hypothesis.affected_resource_id}</span>
        )}
      </div>
      <p>{hypothesis.description}</p>
      <FindingLinks caption="Supporting" labels={hypothesis.supporting_findings} />
      <FindingLinks caption="Contradicting" labels={hypothesis.contradicting_findings} />
    </li>
  );
}

function FindingLinks({ caption, labels }: { caption: string; labels: string[] }) {
  return (
    <p className="muted">
      {caption}:{" "}
      {labels.length === 0
        ? "none"
        : labels.map((label, index) => (
            <span key={`${label}-${index}`}>
              {index > 0 && ", "}
              <Link to={`#${findingAnchor(label)}`}>{label}</Link>
            </span>
          ))}
    </p>
  );
}
