import { CircleCheck, ShieldAlert, TriangleAlert } from "lucide-react";
import type { FindingView } from "../../api/types";
import { percentFromFraction } from "../../lib/format";
import { Badge } from "../../ui/Badge";

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
    <li id={findingAnchor(finding.label)} className="grid gap-2 rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="font-semibold">{finding.label}</strong>
        <span className="text-sm text-muted">
          {finding.category} / {finding.severity} / confidence {percentFromFraction(finding.confidence)}
        </span>
        <Badge tone="neutral">{finding.evidence_strength}</Badge>
        {finding.grounded ? (
          <Badge tone="ok" icon={CircleCheck}>
            grounded
          </Badge>
        ) : (
          <Badge tone="warning" icon={TriangleAlert}>
            ungrounded
          </Badge>
        )}
        {finding.suspected_injection && (
          <Badge tone="critical" icon={ShieldAlert}>
            suspected injection
          </Badge>
        )}
      </div>
      <p className="m-0">{finding.summary}</p>
      {finding.evidence.length > 0 && (
        <div className="grid gap-1">
          <span className="text-sm text-muted">Evidence</span>
          <ul className="m-0 grid list-none gap-1 p-0">
            {finding.evidence.map((item, index) => (
              <li key={index}>
                <code className="break-all text-xs">{JSON.stringify(item)}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
      {finding.counter_evidence.length > 0 && (
        <div className="grid gap-1">
          <span className="text-sm text-muted">Counter-evidence</span>
          <ul className="m-0 list-disc pl-5 text-sm">
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
    return <p className="m-0 text-muted">No findings recorded.</p>;
  }
  return (
    <div className="grid gap-6">
      {groupByAgent(findings).map(([agent, items]) => (
        <div key={agent} className="grid gap-3">
          <h3 className="m-0 text-sm font-semibold">{agent}</h3>
          <ul className="m-0 grid list-none gap-3 p-0">
            {items.map((finding) => (
              <FindingItem key={finding.label} finding={finding} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
