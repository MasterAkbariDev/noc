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
  id: string;
  action_hash: string;
  rung: number;
  authorization: string | null;
  approval_expires_at: string | null;
  dispatched_at: string | null;
  finished_at: string | null;
  result_code: string | null;
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

export type ApprovalDecision = "approved" | "rejected";

export type ApprovalDecisionBody = {
  decision: ApprovalDecision;
  action_hash: string;
  comment: string | null;
};

export type ApprovalView = {
  approval_id: string;
  incident_status: string;
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

export type StreamTicket = {
  ticket: string;
  expires_in: number;
};

export type Role = "viewer" | "operator" | "admin";

export type MeView = {
  username: string;
  role: Role;
  via: "session" | "token";
  totp_enabled?: boolean;
  totp_required?: boolean;
};

export type TotpSetup = {
  secret: string;
  uri: string;
};

export type UserView = {
  id: string;
  username: string;
  role: Role;
  disabled: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type CreateUserBody = {
  username: string;
  password: string;
  role: Role;
};

export type VerdictLevel = "ok" | "working" | "attention" | "degraded" | "down";

export type Verdict = {
  level: VerdictLevel;
  sentence: string;
};

export type Kpis = {
  open_incidents: number;
  needs_you: number;
  servers_up: number;
  servers_total: number;
  llm_keys_ok: number;
  llm_keys_total: number;
};

export type AttentionItem = {
  incident_id: string;
  title: string;
  target: string;
  severity: string;
  status: string;
  status_label: string;
  since: string;
  summary: string;
  advice: string;
};

export type ActivityItem = {
  ts: string;
  kind: "incident" | "audit";
  text: string;
  incident_id: string | null;
  actor: string;
};

export type ServerStatus = "up" | "down" | "unknown";

export type ServerMetrics = {
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  disk_mount: string | null;
};

export type ServerSummary = {
  id: string;
  name: string;
  environment: string;
  automation_level: string;
  automation_label: string;
  halted: boolean;
  status: ServerStatus;
  last_scrape_at: string | null;
  metrics: ServerMetrics | null;
  open_incidents: number;
  worst_severity: string | null;
  headline: string;
};

export type ServiceState = {
  resource_id: string;
  name: string;
  up: boolean | null;
};

export type ServerDetail = ServerSummary & {
  resources: TargetResource[];
  services: ServiceState[];
  recent_incidents: IncidentSummary[];
  last_inventory_at: string | null;
};

export type Overview = {
  verdict: Verdict;
  kpis: Kpis;
  needs_attention: AttentionItem[];
  activity: ActivityItem[];
  servers: ServerSummary[];
};

export type ComponentStatus = "ok" | "degraded" | "down" | "unknown";

export type ComponentHealth = {
  key: string;
  label: string;
  status: ComponentStatus;
  summary: string;
  details: Record<string, string>;
  since: string | null;
};

export type StuckIncident = {
  id: string;
  title: string;
  target: string;
  status: string;
  since: string;
  job_status: string | null;
  job_attempts: number | null;
  job_last_error: string | null;
};

export type SystemHealth = {
  verdict: "ok" | "degraded" | "down";
  checked_at: string;
  components: ComponentHealth[];
  stuck_incidents: StuckIncident[];
};

export type LlmMode = "live" | "record" | "replay";

export type LlmKeyState = "ok" | "cooling" | "rejected" | "unused";

export type LlmModelUsage = {
  tier: string;
  model: string;
  used_today: number;
  daily_limit: number;
};

export type LlmKeyView = {
  label: string;
  provider: string;
  state: LlmKeyState;
  cooling_until: string | null;
  last_error: string | null;
  last_error_at: string | null;
  last_success_at: string | null;
  models: LlmModelUsage[];
};

export type LlmStatus = {
  mode: LlmMode;
  keys: LlmKeyView[];
};

export type StepState = "done" | "current" | "pending" | "skipped" | "failed";

export type StoryStep = {
  key: string;
  label: string;
  state: StepState;
  at: string | null;
};

export type StoryText = {
  text: string;
  technical: string | null;
};

export type StoryPoint = {
  text: string;
  agent: string;
  label: string;
  refs: string[];
  grounded: boolean;
};

export type StoryFound = {
  text: string;
  root_cause_code: string | null;
  root_cause_label: string | null;
  confidence: number | null;
  points: StoryPoint[];
};

export type StoryAction = {
  action: string;
  action_label: string;
  verdict: string;
  verdict_label: string;
  reasons: string[];
  technical: string[];
};

export type StoryDid = {
  text: string;
  considered: StoryAction[];
};

export type StoryAdvice = {
  text: string;
  steps: string[];
};

export type IncidentStory = {
  id: string;
  title: string;
  target: string;
  severity: string;
  status: string;
  status_label: string;
  headline: string;
  steps: StoryStep[];
  what_happened: StoryText;
  what_we_found: StoryFound;
  what_we_did: StoryDid;
  what_you_should_do: StoryAdvice;
};

export type ActivityEntry = {
  id: number;
  ts: string;
  actor: string;
  action: string;
  action_label: string;
  subject: string | null;
  summary: string;
  payload: Record<string, unknown>;
};

export type ActivityPage = {
  items: ActivityEntry[];
  next_before_id: number | null;
};

export type ActivityVerify = {
  ok: boolean;
  broken_at: number | null;
};
