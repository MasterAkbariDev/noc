export type IncidentSummary = {
  id: string;
  title: string;
  status: string;
  severity: string;
  opened_at: string;
  root_cause_code: string | null;
  confidence: number | null;
  escalation_reason: string | null;
};

export type EventView = {
  ts: string;
  type: string;
  actor: string;
  payload: Record<string, unknown>;
};

export type FindingView = {
  label: string;
  agent: string;
  category: string;
  severity: string;
  summary: string;
  evidence: Record<string, unknown>[];
  confidence: number;
  suspected_injection: boolean;
};

export type ActionView = {
  action_type: string;
  resource_id: string;
  status: string;
  permission_class: string;
  eligible: boolean;
  gate_failures: string[];
  reasons: string[];
  impact_score: number;
};

export type IncidentDetail = IncidentSummary & {
  target: string;
  trace_id: string;
  events: EventView[];
  findings: FindingView[];
  actions: ActionView[];
  report_markdown: string | null;
};

export const INCIDENT_STATUSES = [
  "NEW",
  "INVESTIGATING",
  "DIAGNOSED",
  "PLANNED",
  "AWAITING_APPROVAL",
  "REMEDIATING",
  "VERIFYING",
  "RESOLVED",
  "SELF_RESOLVED",
  "ESCALATED",
  "CLOSED",
] as const;
