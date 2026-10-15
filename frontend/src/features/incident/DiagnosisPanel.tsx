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
            term: "Most likely cause",
            detail: <Term technical={diagnosis.primary_code}>{plainLabel(diagnosis.primary_code)}</Term>,
          },
          { key: "confidence", term: "How sure", detail: percentFromFraction(diagnosis.confidence) },
          { key: "security", term: "Looks like an attack", detail: diagnosis.is_security_incident ? "yes" : "no" },
          {
            key: "more",
            term: "To settle it, check",
            detail:
              diagnosis.needs_more_info.length === 0 ? (
                "nothing more is needed"
              ) : (
                <List variant="bullet" gap="xs">
                  {diagnosis.needs_more_info.map((item, index) => (
                    <ListItem key={index}>{item}</ListItem>
                  ))}
                </List>
              ),
          },
          {
            key: "ungrounded",
            term: "Findings thrown away (quote did not match the server)",
            detail: diagnosis.ungrounded_findings,
          },
        ]}
      />
      <h3 className="m-0 text-sm font-semibold">Possible causes, most likely first</h3>
      {ranked.length === 0 ? (
        <p className="m-0 text-muted">No possible causes recorded.</p>
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
        <strong className="font-semibold">
          <Term technical={hypothesis.root_cause_code}>{plainLabel(hypothesis.root_cause_code)}</Term>
        </strong>
        <span className="text-muted">how sure: {percentFromFraction(hypothesis.confidence)}</span>
        {hypothesis.affected_resource_id !== null && (
          <span className="text-muted">on {hypothesis.affected_resource_id.replace(/^[a-z]+:/, "")}</span>
        )}
      </div>
      <p className="m-0">{hypothesis.description}</p>
      <FindingLinks caption="Backed by findings" labels={hypothesis.supporting_findings} />
      <FindingLinks caption="Findings against it" labels={hypothesis.contradicting_findings} />
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
