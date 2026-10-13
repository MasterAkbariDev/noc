export type IncidentSummary = {
  id: string;
  title: string;
  status: string;
  severity: string;
  target: string;
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

export type HypothesisView = {
  root_cause_code: string;
  description: string;
  confidence: number;
  supporting_findings: string[];
  contradicting_findings: string[];
  affected_resource_id: string | null;
};

export type DiagnosisView = {
  primary_code: string;
  confidence: number;
  is_security_incident: boolean;
  hypotheses: HypothesisView[];
  needs_more_info: string[];
  ungrounded_findings: number;
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
  evidence_strength: string;
  counter_evidence: string[];
  grounded: boolean;
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
  high_impact: boolean;
  auto_executable: boolean;
  policy_version: string;
};

export type IncidentDetail = IncidentSummary & {
  trace_id: string;
  mode: string;
  root_cause_summary: string | null;
  resolution_note: string | null;
  investigation_started_at: string | null;
  diagnosed_at: string | null;
  plan_at: string | null;
  escalated_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  diagnosis: DiagnosisView | null;
  events: EventView[];
  findings: FindingView[];
  actions: ActionView[];
  report_markdown: string | null;
};

export type IncidentResolutionBody = {
  resolution_note: string;
  corrected_root_cause_code: string | null;
};

export type AgentRunView = {
  id: string;
  agent: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  rounds: number;
  llm_calls: number;
  tool_calls: number;
  error: string | null;
};

export type ToolCallView = {
  ref: string;
  agent: string;
  tool: string;
  args: Record<string, unknown>;
  permission: string;
  decision: string;
  decision_reason: string | null;
  ok: boolean;
  started_at: string;
  duration_ms: number;
  truncated: boolean;
  injection_flags: string[];
};

export type LlmCallView = {
  id: string;
  agent: string;
  tier: string;
  provider: string;
  model: string;
  mode: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  wait_ms: number;
  fallback: boolean;
  finish_reason: string | null;
  redactions: number;
  error: string | null;
  created_at: string;
};

export type IncidentTrace = {
  agent_runs: AgentRunView[];
  tool_calls: ToolCallView[];
  llm_calls: LlmCallView[];
};

export type TargetResource = {
  resource_id: string;
  kind: string;
  name: string;
};

export type TargetView = {
  id: string;
  name: string;
  environment: string;
  automation_level: string;
  halted: boolean;
  last_inventory_at: string | null;
  resources: TargetResource[];
};

export type StreamTicket = {
  ticket: string;
  expires_in: number;
};

export type IncidentEventMessage = {
  incident_id: string;
  id: number;
  ts: string;
  type: string;
  actor: string;
  payload: Record<string, unknown>;
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
