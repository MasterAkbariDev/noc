import { Link } from "react-router";
import type { DiagnosisView, HypothesisView } from "../../api/types";
import { percentFromFraction } from "../../lib/format";
import { findingAnchor } from "./FindingsList";

export function DiagnosisPanel({ diagnosis }: { diagnosis: DiagnosisView | null }) {
  if (diagnosis === null) {
    return <p className="m-0 text-muted">Diagnosis not yet recorded.</p>;
  }
  const ranked = [...diagnosis.hypotheses].sort((a, b) => b.confidence - a.confidence);
  return (
    <div className="grid gap-4">
      <dl className="m-0 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted">Primary cause</dt>
        <dd className="m-0">
          <code>{diagnosis.primary_code}</code>
        </dd>
        <dt className="text-muted">Confidence</dt>
        <dd className="m-0">{percentFromFraction(diagnosis.confidence)}</dd>
        <dt className="text-muted">Security incident</dt>
        <dd className="m-0">{diagnosis.is_security_incident ? "yes" : "no"}</dd>
        <dt className="text-muted">Needs more info</dt>
        <dd className="m-0">{diagnosis.needs_more_info.join(", ") || "-"}</dd>
        <dt className="text-muted">Ungrounded findings</dt>
        <dd className="m-0">{diagnosis.ungrounded_findings}</dd>
      </dl>
      <h3 className="m-0 text-sm font-semibold">Hypotheses, most likely first</h3>
      {ranked.length === 0 ? (
        <p className="m-0 text-muted">No hypotheses recorded.</p>
      ) : (
        <ol className="m-0 grid list-none gap-3 p-0">
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
    <li className="hypothesis grid gap-2 rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <code className="font-semibold">{hypothesis.root_cause_code}</code>
        <span className="text-muted">confidence {percentFromFraction(hypothesis.confidence)}</span>
        {hypothesis.affected_resource_id !== null && (
          <span className="text-muted">resource {hypothesis.affected_resource_id}</span>
        )}
      </div>
      <p className="m-0">{hypothesis.description}</p>
      <FindingLinks caption="Supporting" labels={hypothesis.supporting_findings} />
      <FindingLinks caption="Contradicting" labels={hypothesis.contradicting_findings} />
    </li>
  );
}

function FindingLinks({ caption, labels }: { caption: string; labels: string[] }) {
  return (
    <p className="m-0 text-sm text-muted">
      {caption}:{" "}
      {labels.length === 0
        ? "none"
        : labels.map((label, index) => (
            <span key={`${label}-${index}`}>
              {index > 0 && ", "}
              <Link to={`#${findingAnchor(label)}`} className="text-accent underline">
                {label}
              </Link>
            </span>
          ))}
    </p>
  );
}
