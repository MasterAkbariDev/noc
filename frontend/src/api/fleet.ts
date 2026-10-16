import { apiGet, apiPost } from "./client";

export type SshKeyPurpose = "bootstrap" | "ops" | "operator-shell";
export type FleetEnvironment = "lab" | "prod";
export type SshKeyState = "active" | "rotate_soon" | "rotating" | "expired" | "retired";

export type CommandStep = { title: string; where: string; command: string };
export type CommandSteps = { steps: CommandStep[] };

export type SshKey = {
  id: string;
  label: string;
  purpose: SshKeyPurpose;
  environment: FleetEnvironment;
  public_key: string;
  fingerprint: string;
  from_pin: string | null;
  forced_command: string | null;
  has_passphrase: boolean;
  rotation_days: number;
  created_at: string;
  created_by: string;
  expires_at: string;
  rotation_due_at: string;
  state: SshKeyState;
  replaces_id: string | null;
  retired_at: string | null;
  hosts: string[];
};

export type InstalledKey = {
  key_id: string;
  label: string;
  purpose: SshKeyPurpose;
  fingerprint: string;
  installed_at: string;
  expires_at: string;
  rotation_due_at: string;
  state: SshKeyState;
  sudo_scope_ok: boolean;
};

export type FleetRow = {
  host_id: string | null;
  target_id: string | null;
  name: string;
  address: string;
  ssh_port: number | null;
  ssh_user: string | null;
  environment: FleetEnvironment;
  reachable: boolean | null;
  helper_up: boolean | null;
  helper_version: string | null;
  keys: InstalledKey[];
  automation_level: string | null;
  automation_label: string | null;
  notes: string[];
};

export type SshKeyRule = {
  purpose: SshKeyPurpose;
  default_days: number;
  min_days: number;
  max_days: number;
  needs_pin: boolean;
  allows_forced_command: boolean;
  has_paste_command: boolean;
};

export type ForcedCommand = { name: string; command: string };

export type Fleet = {
  secrets_persistent: boolean;
  metrics_available: boolean;
  hosts: FleetRow[];
  keys: SshKey[];
  rules: SshKeyRule[];
  forced_commands: ForcedCommand[];
};

export type Rotation = { new_key: SshKey; steps: CommandStep[] };

export type AddHostBody = {
  name: string;
  address: string;
  ssh_port: number;
  ssh_user: string;
  environment: FleetEnvironment;
  totp: string;
};

export type GenerateKeyBody = {
  label: string;
  purpose: SshKeyPurpose;
  environment: FleetEnvironment;
  from_pin: string | null;
  forced_command: string | null;
  with_passphrase: boolean;
  rotation_days: number | null;
  totp: string;
};

function segment(id: string): string {
  return encodeURIComponent(id);
}

export function getFleet(): Promise<Fleet> {
  return apiGet<Fleet>("/api/fleet");
}

export function addFleetHost(body: AddHostBody): Promise<void> {
  return apiPost<void>("/api/fleet/hosts", body);
}

export function offboardFleetHost(hostId: string, totp: string): Promise<CommandSteps> {
  return apiPost<CommandSteps>(`/api/fleet/hosts/${segment(hostId)}/offboard`, { totp });
}

export function getPasteCommand(hostId: string, keyId: string): Promise<CommandSteps> {
  return apiPost<CommandSteps>(`/api/fleet/hosts/${segment(hostId)}/paste-command`, { key_id: keyId });
}

export function markKeyInstalled(hostId: string, keyId: string, sudoScopeOk: boolean, totp: string): Promise<void> {
  return apiPost<void>(`/api/fleet/hosts/${segment(hostId)}/installed`, {
    key_id: keyId,
    sudo_scope_ok: sudoScopeOk,
    totp,
  });
}

export function generateSshKey(body: GenerateKeyBody): Promise<SshKey> {
  return apiPost<SshKey>("/api/fleet/keys", body);
}

export function rotateSshKey(keyId: string, totp: string): Promise<Rotation> {
  return apiPost<Rotation>(`/api/fleet/keys/${segment(keyId)}/rotate`, { totp });
}

export function finishSshKeyRotation(keyId: string, totp: string): Promise<SshKey> {
  return apiPost<SshKey>(`/api/fleet/keys/${segment(keyId)}/finish-rotation`, { totp });
}

export function revokeSshKey(keyId: string, totp: string): Promise<CommandSteps> {
  return apiPost<CommandSteps>(`/api/fleet/keys/${segment(keyId)}/revoke`, { totp });
}
