import { ApiError } from "../../api/client";
import type { ActionView, Role } from "../../api/types";
import { errorMessage } from "../../lib/format";

export const COMMENT_MAX_LENGTH = 500;

export const CHANGED_REQUEST_TEXT = "This request changed or expired — reload the incident.";

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

export function pendingApprovals(actions: ActionView[]): ActionView[] {
  return actions.filter((action) => action.status === "pending_approval");
}

export function canDecideActions(role: Role): boolean {
  return role === "operator" || role === "admin";
}

export function isExpired(expiresAt: string | null, now: number): boolean {
  if (expiresAt === null) {
    return false;
  }
  const expires = Date.parse(expiresAt);
  return Number.isNaN(expires) || expires <= now;
}

export function expiryText(expiresAt: string, now: number): string {
  if (isExpired(expiresAt, now)) {
    return "Expired";
  }
  const remaining = Date.parse(expiresAt) - now;
  if (remaining < MINUTE_MS) {
    return "Expires in under a minute";
  }
  if (remaining < HOUR_MS) {
    return `Expires in ${Math.floor(remaining / MINUTE_MS)} min`;
  }
  if (remaining < DAY_MS) {
    return `Expires in ${Math.floor(remaining / HOUR_MS)} h`;
  }
  const days = Math.floor(remaining / DAY_MS);
  return days === 1 ? "Expires in 1 day" : `Expires in ${days} days`;
}

export function decisionErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    return CHANGED_REQUEST_TEXT;
  }
  if (error instanceof ApiError && error.status === 422) {
    return error.detail;
  }
  return errorMessage(error);
}
