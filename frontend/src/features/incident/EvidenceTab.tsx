import type { IncidentDetail } from "../../api/types";
import { Section } from "../../ui/Section";
import { DiagnosisPanel } from "./DiagnosisPanel";
import { FindingsList } from "./FindingsList";
import { PolicyTable } from "./PolicyTable";

export function EvidenceTab({ incident }: { incident: IncidentDetail }) {
  return (
    <div className="grid gap-8">
      <Section heading="Diagnosis">
        <DiagnosisPanel diagnosis={incident.diagnosis} />
      </Section>
      <Section heading="Findings">
        <FindingsList findings={incident.findings} />
      </Section>
      <Section heading="Policy decisions">
        <PolicyTable actions={incident.actions} />
      </Section>
    </div>
  );
}
