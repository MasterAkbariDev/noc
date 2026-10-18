import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  generateSshKey,
  getFleet,
  getPasteCommand,
  markKeyInstalled,
  revokeSshKey,
  type Fleet,
  type FleetRow,
  type SshKey,
} from "../api/fleet";
import { useSession } from "../auth/session";
import { sessionFor } from "../features/settings/fixtures";
import { renderWithProviders } from "../features/settings/harness";
import { FleetPage } from "./FleetPage";

vi.mock("../api/fleet", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/fleet")>()),
  getFleet: vi.fn(),
  generateSshKey: vi.fn(),
  getPasteCommand: vi.fn(),
  markKeyInstalled: vi.fn(),
  revokeSshKey: vi.fn(),
}));

vi.mock("../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../auth/session")>()),
  useSession: vi.fn(),
}));

const OPS_KEY: SshKey = {
  id: "key-1",
  label: "lab ops",
  purpose: "ops",
  environment: "lab",
  public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOps",
  fingerprint: "SHA256:abcdefghijklmnopqrstuvwxyz0123456789",
  from_pin: "198.51.100.4",
  forced_command: null,
  has_passphrase: true,
  rotation_days: 90,
  created_at: "2026-10-01T10:00:00Z",
  created_by: "admin",
  expires_at: "2026-12-30T10:00:00Z",
  rotation_due_at: "2026-12-16T10:00:00Z",
  state: "active",
  replaces_id: null,
  retired_at: null,
  hosts: ["demo-2"],
};

const MONITORED: FleetRow = {
  host_id: null,
  target_id: "t-1",
  name: "demo-1",
  address: "10.0.0.2",
  ssh_port: null,
  ssh_user: null,
  environment: "lab",
  reachable: true,
  helper_up: true,
  helper_version: "0.2.0",
  keys: [],
  automation_level: "auto_safe",
  automation_label: "Fixes safe problems",
  notes: ["Monitored, but no SSH details yet: add it to the fleet to manage keys."],
};

const NEW_HOST: FleetRow = {
  ...MONITORED,
  host_id: "h-2",
  target_id: null,
  name: "demo-2",
  address: "203.0.113.7",
  ssh_port: 22,
  ssh_user: "ops",
  reachable: null,
  helper_up: null,
  helper_version: null,
  automation_level: null,
  automation_label: null,
  notes: [],
};

function fleet(changes: Partial<Fleet> = {}): Fleet {
  return {
    secrets_persistent: true,
    metrics_available: true,
    hosts: [MONITORED, NEW_HOST],
    keys: [OPS_KEY],
    rules: [
      { purpose: "bootstrap", default_days: 1, min_days: 1, max_days: 7, needs_pin: false, allows_forced_command: false, has_paste_command: true },
      { purpose: "ops", default_days: 90, min_days: 7, max_days: 365, needs_pin: true, allows_forced_command: true, has_paste_command: true },
      { purpose: "operator-shell", default_days: 30, min_days: 1, max_days: 90, needs_pin: true, allows_forced_command: false, has_paste_command: false },
    ],
    forced_commands: [{ name: "helper-status", command: "/usr/bin/systemctl is-active noc-sentinel.service" }],
    ...changes,
  };
}

function openSshTab() {
  fireEvent.mouseDown(screen.getByRole("tab", { name: /SSH hosts/ }), { button: 0, ctrlKey: false });
}

function renderAs(role: "viewer" | "operator" | "admin") {
  vi.mocked(useSession).mockReturnValue(sessionFor({ username: "admin", role, via: "session" }));
  const view = renderWithProviders(<FleetPage />);
  if (role === "admin") {
    openSshTab();
  }
  return view;
}

beforeEach(() => {
  for (const mock of [getFleet, generateSshKey, getPasteCommand, markKeyInstalled, revokeSshKey]) {
    vi.mocked(mock).mockReset();
  }
  vi.mocked(getFleet).mockResolvedValue(fleet());
});

afterEach(() => {
  cleanup();
});

describe("FleetPage", () => {
  it("tells non-admins to ask an admin and loads nothing", () => {
    renderAs("operator");
    expect(screen.getByText("Only admins manage the fleet")).toBeTruthy();
    expect(getFleet).not.toHaveBeenCalled();
  });

  it("lists monitored targets and added servers with their status", async () => {
    renderAs("admin");
    const servers = await screen.findByRole("table", { name: "Server status" });
    expect(within(servers).getByText("Up · 0.2.0")).toBeTruthy();
    expect(within(servers).getByText("ops@203.0.113.7:22")).toBeTruthy();
    expect(within(servers).getByRole("button", { name: "Add SSH details for demo-1" })).toBeTruthy();
    expect(within(servers).getByRole("button", { name: "Set up demo-2" })).toBeTruthy();
    const keys = screen.getByRole("table", { name: "Key list" });
    expect(within(keys).getByText("from 198.51.100.4 · passphrase")).toBeTruthy();
  });

  it("never shows anything that looks like a private key", async () => {
    const { container } = renderAs("admin");
    await screen.findByRole("table", { name: "Server status" });
    expect(container.textContent).not.toContain("PRIVATE KEY");
  });

  it("shows the paste command and sends the code when marking a key installed", async () => {
    vi.mocked(getPasteCommand).mockResolvedValue({
      steps: [{ title: "Create the ops user and allow the key", where: "on demo-2, as root", command: "id -u ops" }],
    });
    vi.mocked(markKeyInstalled).mockResolvedValue(undefined);
    renderAs("admin");
    fireEvent.click(await screen.findByRole("button", { name: "Set up demo-2" }));

    expect(await screen.findByText("id -u ops")).toBeTruthy();
    expect(getPasteCommand).toHaveBeenCalledWith("h-2", "key-1");
    fireEvent.click(screen.getByRole("checkbox", { name: /sudo scope OK/ }));
    fireEvent.change(screen.getByRole("textbox", { name: /Authentication code/ }), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark as installed" }));

    await waitFor(() => expect(markKeyInstalled).toHaveBeenCalledWith("h-2", "key-1", true, "123456"));
  });

  it("shows the cleanup commands after a revoke", async () => {
    vi.mocked(revokeSshKey).mockResolvedValue({
      steps: [{ title: "Remove the key line", where: "on demo-2, as root", command: "sed -i '/ noc-key-key-1$/d'" }],
    });
    renderAs("admin");
    fireEvent.click(await screen.findByRole("button", { name: "Revoke lab ops" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Authentication code/ }), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Revoke key" }));

    expect(await screen.findByText("sed -i '/ noc-key-key-1$/d'")).toBeTruthy();
    expect(revokeSshKey).toHaveBeenCalledWith("key-1", "654321");
  });

  it("warns when the secrets folder is not persistent", async () => {
    vi.mocked(getFleet).mockResolvedValue(fleet({ secrets_persistent: false }));
    renderAs("admin");
    expect(await screen.findByText("Keys would be lost on a container rebuild")).toBeTruthy();
  });
});
