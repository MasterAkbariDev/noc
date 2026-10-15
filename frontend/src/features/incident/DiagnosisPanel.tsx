import { Link } from "react-router";
import type { DiagnosisView, HypothesisView } from "../../api/types";
import { percentFromFraction } from "../../lib/format";
import { DescriptionList, List, ListItem } from "../../ui/List";
import { Term } from "../../ui/Term";
import { findingAnchor } from "./FindingsList";
import { plainLabel } from "./labels";

export function DiagnosisPanel({ diagnosis }: { diagnosis: DiagnosisView | null }) {
  if (diagnosis === null) {
    return <p className="m-0 text-muted">Diagnosis not yet recorded.</p>;
  }
  const ranked = [...diagnosis.hypotheses].sort((a, b) => b.confidence - a.confidence);
  return (
    <div className="grid gap-4">
      <DescriptionList
        items={[
          {
            key: "primary",
            term: "Primary cause",
            detail: <Term technical={diagnosis.primary_code}>{plainLabel(diagnosis.primary_code)}</Term>,
          },
          { key: "confidence", term: "Confidence", detail: percentFromFraction(diagnosis.confidence) },
          { key: "security", term: "Security incident", detail: diagnosis.is_security_incident ? "yes" : "no" },
          { key: "more", term: "Needs more info", detail: diagnosis.needs_more_info.join(", ") || "-" },
          { key: "ungrounded", term: "Ungrounded findings", detail: diagnosis.ungrounded_findings },
        ]}
      />
      <h3 className="m-0 text-sm font-semibold">Hypotheses, most likely first</h3>
      {ranked.length === 0 ? (
        <p className="m-0 text-muted">No hypotheses recorded.</p>
      ) : (
        <List ordered>
          {ranked.map((hypothesis, index) => (
            <HypothesisItem key={`${hypothesis.root_cause_code}-${index}`} hypothesis={hypothesis} />
          ))}
        </List>
      )}
    </div>
  );
}

function HypothesisItem({ hypothesis }: { hypothesis: HypothesisView }) {
  return (
    <ListItem className="hypothesis grid gap-2 rounded-card border border-border bg-surface p-4">
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
    </ListItem>
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
