import type { ActivityItem, AttentionItem, Overview, ServerSummary } from "../../api/types";

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
    },
    needs_attention: [attentionItem()],
    activity: [activityItem()],
    servers: [serverSummary()],
    ...overrides,
  };
}
