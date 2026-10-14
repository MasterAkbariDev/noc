import type { IncidentSummary, ServerDetail, ServerSummary } from "../../api/types";

export const SERVER_ID = "11111111-1111-1111-1111-111111111111";
export const HOSTILE_TEXT = "<img src=x onerror=alert(1)>";

export function summaryFixture(overrides: Partial<ServerSummary> = {}): ServerSummary {
  return {
    id: SERVER_ID,
    name: "web-1",
    environment: "staging",
    automation_level: "auto_safe",
    automation_label: "Safe fixes run automatically",
    halted: false,
    status: "up",
    last_scrape_at: "2026-10-13T09:59:00Z",
    metrics: { cpu_percent: 42, memory_percent: 55.5, disk_percent: 92, disk_mount: "/var" },
    open_incidents: 1,
    worst_severity: "critical",
    headline: "Disk 92% full · 1 open incident",
    ...overrides,
  };
}

export function incidentFixture(overrides: Partial<IncidentSummary> = {}): IncidentSummary {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    title: "Disk filling on web-1",
    status: "ESCALATED",
    severity: "critical",
    target: "web-1",
    opened_at: "2026-10-13T09:00:00Z",
    root_cause_code: null,
    confidence: null,
    escalation_reason: null,
    ...overrides,
  };
}

export function detailFixture(overrides: Partial<ServerDetail> = {}): ServerDetail {
  return {
    ...summaryFixture(),
    resources: [{ resource_id: "svc-web", kind: "systemd_unit", name: "nginx.service" }],
    services: [{ resource_id: "svc-web", name: "nginx", up: true }],
    recent_incidents: [incidentFixture()],
    last_inventory_at: "2026-10-13T09:58:00Z",
    ...overrides,
  };
}
