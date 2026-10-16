import { describe, expect, it } from "vitest";
import type { FleetRow, SshKey } from "../../api/fleet";
import { dayDistance, finishesRotation, helperView, sudoView, waitingRotation } from "./view";

const NOW = new Date("2026-10-16T12:00:00Z");

function key(id: string, changes: Partial<SshKey> = {}): SshKey {
  return {
    id,
    label: id,
    purpose: "ops",
    environment: "lab",
    public_key: "ssh-ed25519 AAAA",
    fingerprint: "SHA256:x",
    from_pin: null,
    forced_command: null,
    has_passphrase: false,
    rotation_days: 90,
    created_at: "2026-10-01T00:00:00Z",
    created_by: "admin",
    expires_at: "2026-12-30T00:00:00Z",
    rotation_due_at: "2026-12-16T00:00:00Z",
    state: "active",
    replaces_id: null,
    retired_at: null,
    hosts: [],
    ...changes,
  };
}

const ROW: FleetRow = {
  host_id: "h",
  target_id: "t",
  name: "demo-1",
  address: "10.0.0.2",
  ssh_port: 22,
  ssh_user: "ops",
  environment: "lab",
  reachable: true,
  helper_up: false,
  helper_version: "0.2.0",
  keys: [],
  automation_level: null,
  automation_label: null,
  notes: [],
};

describe("fleet view", () => {
  it("says how far away a date is in whole days", () => {
    expect(dayDistance("2026-10-16T13:00:00Z", NOW)).toBe("today");
    expect(dayDistance("2026-10-26T12:00:00Z", NOW)).toBe("in 10 days");
    expect(dayDistance("2026-10-15T12:00:00Z", NOW)).toBe("1 day ago");
  });

  it("reads the helper state with its version", () => {
    expect(helperView(ROW)).toEqual({ label: "Down · 0.2.0", tone: "critical" });
    expect(helperView({ ...ROW, target_id: null })).toEqual({ label: "Not set up", tone: "neutral" });
  });

  it("flags sudo only when a key was installed with sudo rights", () => {
    expect(sudoView(ROW).label).toBe("Not checked");
    const installed = { key_id: "k", label: "k", purpose: "ops" as const, fingerprint: "f", installed_at: "", expires_at: "", rotation_due_at: "", state: "active" as const };
    expect(sudoView({ ...ROW, keys: [{ ...installed, sudo_scope_ok: true }] }).label).toBe("No sudo");
    expect(sudoView({ ...ROW, keys: [{ ...installed, sudo_scope_ok: false }] }).label).toBe("Check sudoers");
  });

  it("knows a rotation is waiting until the old key is retired", () => {
    const old = key("old");
    const fresh = key("new", { replaces_id: "old" });
    expect(waitingRotation([old, fresh], old)).toBe(fresh);
    expect(finishesRotation([old, fresh], fresh)).toBe(true);
    expect(finishesRotation([{ ...old, retired_at: "2026-10-16T00:00:00Z" }, fresh], fresh)).toBe(false);
  });
});
