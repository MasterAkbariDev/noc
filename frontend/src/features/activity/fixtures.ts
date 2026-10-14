import type { ActivityEntry } from "../../api/types";

export const HOSTILE_TEXT = '<img src=x onerror="alert(1)"><script>alert(1)</script>';

export function entryFixture(overrides: Partial<ActivityEntry> = {}): ActivityEntry {
  return {
    id: 1,
    ts: "2026-10-13T10:00:00Z",
    actor: "alice",
    action: "incident_closed",
    action_label: "Incident closed",
    subject: "3f2a",
    summary: "alice closed incident 3f2a",
    payload: { incident_id: "3f2a", note: "fixed" },
    ...overrides,
  };
}
