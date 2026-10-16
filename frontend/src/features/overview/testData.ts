import type { ActivityItem, AttentionItem, FixedItem, Metrics, Overview, ServerSummary, SystemHealth } from "../../api/types";

export const HOSTILE_IMG = "<img src=x onerror=alert(1)>";
export const HOSTILE_SCRIPT = "<script>alert(1)</script>";

export function attentionItem(overrides: Partial<AttentionItem> = {}): AttentionItem {
  return {
    incident_id: "11111111-1111-1111-1111-111111111111",
    title: "Disk almost full on demo-1",
    target: "demo-1",
    severity: "critical",
    status: "ESCALATED",
    status_label: "Needs you",
    since: "2026-10-14T10:00:00Z",
    summary: "Logs are filling the root disk.",
    advice: "Review the logs and free space.",
    ...overrides,
  };
}

export function fixedItem(overrides: Partial<FixedItem> = {}): FixedItem {
  return {
    incident_id: "33333333-3333-3333-3333-333333333333",
    title: "demo-shop.service stopped",
    target: "demo-1",
    resolved_at: "2026-10-14T09:00:00Z",
    kind: "automatic",
    sentence: "The NOC chose to start service on demo-shop and did it on its own. The check afterwards passed.",
    ...overrides,
  };
}

export function serverSummary(overrides: Partial<ServerSummary> = {}): ServerSummary {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    name: "demo-1",
    environment: "lab",
    automation_level: "observe",
    automation_label: "Watch only",
    halted: false,
    status: "up",
    last_scrape_at: "2026-10-14T10:00:00Z",
    metrics: null,
    open_incidents: 1,
    worst_severity: "critical",
    headline: "Disk 92% full",
    ...overrides,
  };
}

export function activityItem(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    ts: "2026-10-14T10:00:00Z",
    kind: "incident",
    text: "Incident opened: DiskAlmostFull",
    incident_id: "11111111-1111-1111-1111-111111111111",
    actor: "noc",
    ...overrides,
  };
}

export function overviewFixture(overrides: Partial<Overview> = {}): Overview {
  return {
    verdict: { level: "attention", sentence: "1 incident needs you" },
    kpis: {
      open_incidents: 1,
      needs_you: 1,
      servers_up: 2,
      servers_total: 2,
      llm_keys_ok: 9,
      llm_keys_total: 10,
      fixed_today: 2,
      fixed_automatically_today: 1,
    },
    needs_attention: [attentionItem()],
    fixed: [fixedItem()],
    activity: [activityItem()],
    servers: [serverSummary()],
    ...overrides,
  };
}

export function metricsFixture(overrides: Partial<Metrics> = {}): Metrics {
  return {
    days: 14,
    since: "2026-10-01T00:00:00Z",
    totals: {
      incidents: 4,
      resolved: 2,
      escalated: 1,
      open: 1,
      auto_resolved_share: 0.5,
      median_minutes_to_resolve: 12,
      median_minutes_to_diagnose: 3,
      llm_calls: 30,
      llm_failures: 0,
      tokens: 12000,
      tool_calls: 40,
      actions_run: 2,
      reviewed: 1,
      confirmed: 1,
    },
    per_day: [
      { day: "2026-10-13", opened: 1, resolved: 1, escalated: 0, llm_calls: 10, tokens: 4000, tool_calls: 12 },
      { day: "2026-10-14", opened: 3, resolved: 1, escalated: 1, llm_calls: 20, tokens: 8000, tool_calls: 28 },
    ],
    root_causes: [
      { label: "disk_full_logs", count: 3 },
      { label: "service_crashed", count: 1 },
    ],
    outcomes: [
      { label: "RESOLVED", count: 2 },
      { label: "ESCALATED", count: 1 },
    ],
    actions: [],
    variants: [],
    ...overrides,
  };
}

export function systemHealthFixture(overrides: Partial<SystemHealth> = {}): SystemHealth {
  return {
    verdict: "ok",
    checked_at: "2026-10-14T10:00:00Z",
    components: [
      { key: "database", label: "Database", status: "ok", summary: "The database answers queries", details: {}, since: null },
      { key: "worker", label: "Worker", status: "down", summary: "The worker has never reported", details: {}, since: null },
    ],
    stuck_incidents: [],
    ...overrides,
  };
}
