import type { ActivityQuery } from "../../api/client";

export const ACTIVITY_PAGE_SIZE = 50;
export const ACTOR_MAX_LENGTH = 64;

export type ActivityActionOption = { value: string; label: string };

export const ACTIVITY_ACTIONS: readonly ActivityActionOption[] = [
  { value: "user_created", label: "User created" },
  { value: "user_disabled", label: "User disabled" },
  { value: "user_enabled", label: "User enabled" },
  { value: "user_role_changed", label: "Role changed" },
  { value: "user_password_reset", label: "Password reset by an admin" },
  { value: "password_changed", label: "Password changed" },
  { value: "login", label: "Signed in" },
  { value: "logout", label: "Signed out" },
  { value: "login_failed", label: "Failed sign-in" },
  { value: "incident_closed", label: "Incident closed" },
  { value: "target_added", label: "Target added" },
  { value: "target_automation_set", label: "Automation level changed" },
  { value: "target_auto_actions_set", label: "Automatic actions changed" },
  { value: "target_profile_set", label: "Service profile changed" },
  { value: "scenario_run_started", label: "Chaos scenario started" },
  { value: "scenario_run_finished", label: "Chaos scenario finished" },
];

export type ActivityFilters = { action: string; actor: string };

export const NO_FILTERS: ActivityFilters = { action: "", actor: "" };

export function isKnownAction(value: string): boolean {
  return ACTIVITY_ACTIONS.some((option) => option.value === value);
}

export function parseActivityFilters(params: URLSearchParams): ActivityFilters {
  const action = params.get("action") ?? "";
  const actor = (params.get("actor") ?? "").trim().slice(0, ACTOR_MAX_LENGTH);
  return { action: isKnownAction(action) ? action : "", actor };
}

export function activitySearchParams(filters: ActivityFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.action !== "") {
    params.set("action", filters.action);
  }
  if (filters.actor !== "") {
    params.set("actor", filters.actor);
  }
  return params;
}

export function activityQuery(filters: ActivityFilters, beforeId: number | undefined): ActivityQuery {
  return {
    limit: ACTIVITY_PAGE_SIZE,
    before_id: beforeId,
    action: filters.action === "" ? undefined : filters.action,
    actor: filters.actor === "" ? undefined : filters.actor,
  };
}
