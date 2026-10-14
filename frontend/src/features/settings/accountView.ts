import { ApiError } from "../../api/client";
import type { Role } from "../../api/types";
import type { ToneView } from "../../lib/tones";

export const ROLE_OPTIONS: readonly Role[] = ["viewer", "operator", "admin"];

const ROLE_LABELS: Record<Role, string> = {
  viewer: "Viewer",
  operator: "Operator",
  admin: "Admin",
};

export const NETWORK_FAILURE_TEXT = "The NOC could not be reached. Try again.";
export const OWN_ROLE_REASON = "You cannot change your own role.";
export const OWN_ACCOUNT_REASON = "You cannot disable or reset your own account here. Use My account instead.";

export function roleLabel(role: Role): string {
  return ROLE_LABELS[role];
}

export function parseRole(value: string): Role | null {
  return ROLE_OPTIONS.find((role) => role === value) ?? null;
}

export function accountStatusView(disabled: boolean): ToneView {
  return disabled ? { label: "Disabled", tone: "critical" } : { label: "Active", tone: "ok" };
}

export function settingsErrorText(error: unknown): string {
  return error instanceof ApiError ? error.detail : NETWORK_FAILURE_TEXT;
}
