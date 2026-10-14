import type {
  ActivityPage,
  ActivityVerify,
  ApprovalDecisionBody,
  ApprovalView,
  CreateUserBody,
  IncidentDetail,
  IncidentResolutionBody,
  IncidentStory,
  IncidentSummary,
  IncidentTrace,
  LlmStatus,
  MeView,
  Overview,
  Role,
  ServerDetail,
  ServerSummary,
  StreamTicket,
  SystemHealth,
  TargetView,
  UserView,
} from "./types";

export type ActivityQuery = {
  limit?: number;
  before_id?: number;
  action?: string;
  actor?: string;
};

export const CSRF_COOKIE = "noc_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

const PATHS_WITHOUT_SESSION_EXPIRY: ReadonlySet<string> = new Set([
  "/api/auth/login",
  "/api/auth/me",
  "/api/auth/password",
]);

let unauthorizedHandler: (() => void) | null = null;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

function readCsrfToken(): string {
  const prefix = `${CSRF_COOKIE}=`;
  const part = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix));
  return part === undefined ? "" : part.slice(prefix.length);
}

function pathname(path: string): string {
  return path.split("?", 1)[0] ?? path;
}

async function errorDetail(response: Response): Promise<string> {
  const fallback = `${response.status} ${response.statusText}`.trim();
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
    return fallback;
  } catch {
    return fallback;
  }
}

async function apiRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (method !== "GET") {
    headers[CSRF_HEADER] = readCsrfToken();
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = new ApiError(response.status, await errorDetail(response));
    if (response.status === 401 && !PATHS_WITHOUT_SESSION_EXPIRY.has(pathname(path))) {
      unauthorizedHandler?.();
    }
    throw error;
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>("GET", path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>("POST", path, body);
}

export function login(username: string, password: string): Promise<MeView> {
  return apiPost<MeView>("/api/auth/login", { username, password });
}

export function logout(): Promise<void> {
  return apiPost<void>("/api/auth/logout", {});
}

export function getMe(): Promise<MeView> {
  return apiGet<MeView>("/api/auth/me");
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return apiPost<void>("/api/auth/password", { current_password: currentPassword, new_password: newPassword });
}

export function listIncidents(status?: string): Promise<IncidentSummary[]> {
  const query = status ? `?${new URLSearchParams({ status })}` : "";
  return apiGet<IncidentSummary[]>(`/api/incidents${query}`);
}

export function getIncident(id: string): Promise<IncidentDetail> {
  return apiGet<IncidentDetail>(`/api/incidents/${encodeURIComponent(id)}`);
}

export function getTrace(id: string): Promise<IncidentTrace> {
  return apiGet<IncidentTrace>(`/api/incidents/${encodeURIComponent(id)}/trace`);
}

export function getTargets(): Promise<TargetView[]> {
  return apiGet<TargetView[]>("/api/targets");
}

export function closeIncident(id: string, body: IncidentResolutionBody): Promise<IncidentSummary> {
  return apiPost<IncidentSummary>(`/api/incidents/${encodeURIComponent(id)}/close`, body);
}

export async function fetchStreamTicket(): Promise<string> {
  const issued = await apiPost<StreamTicket>("/api/events/ticket", {});
  return issued.ticket;
}

function queryString(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).flatMap(([key, value]) =>
    value === undefined ? [] : [[key, String(value)]],
  );
  return entries.length === 0 ? "" : `?${new URLSearchParams(entries)}`;
}

function encodedId(id: string): string {
  return encodeURIComponent(id);
}

export function getOverview(): Promise<Overview> {
  return apiGet<Overview>("/api/overview");
}

export function getSystemHealth(): Promise<SystemHealth> {
  return apiGet<SystemHealth>("/api/system/health");
}

export function getLlmStatus(): Promise<LlmStatus> {
  return apiGet<LlmStatus>("/api/system/llm");
}

export function getStory(id: string): Promise<IncidentStory> {
  return apiGet<IncidentStory>(`/api/incidents/${encodedId(id)}/story`);
}

export function getServers(): Promise<ServerSummary[]> {
  return apiGet<ServerSummary[]>("/api/servers");
}

export function getServer(id: string): Promise<ServerDetail> {
  return apiGet<ServerDetail>(`/api/servers/${encodedId(id)}`);
}

export function getActivity(query: ActivityQuery = {}): Promise<ActivityPage> {
  return apiGet<ActivityPage>(`/api/activity${queryString(query)}`);
}

export function verifyActivity(): Promise<ActivityVerify> {
  return apiGet<ActivityVerify>("/api/activity/verify");
}

export function getUsers(): Promise<UserView[]> {
  return apiGet<UserView[]>("/api/users");
}

export function createUser(body: CreateUserBody): Promise<UserView> {
  return apiPost<UserView>("/api/users", body);
}

export function setUserRole(id: string, role: Role): Promise<UserView> {
  return apiPost<UserView>(`/api/users/${encodedId(id)}/role`, { role });
}

export function disableUser(id: string): Promise<UserView> {
  return apiPost<UserView>(`/api/users/${encodedId(id)}/disable`, {});
}

export function enableUser(id: string): Promise<UserView> {
  return apiPost<UserView>(`/api/users/${encodedId(id)}/enable`, {});
}

export function resetUserPassword(id: string, newPassword: string): Promise<UserView> {
  return apiPost<UserView>(`/api/users/${encodedId(id)}/password`, { new_password: newPassword });
}

export function decideOnAction(
  incidentId: string,
  actionId: string,
  body: ApprovalDecisionBody,
): Promise<ApprovalView> {
  return apiPost<ApprovalView>(
    `/api/incidents/${encodedId(incidentId)}/actions/${encodedId(actionId)}/decision`,
    body,
  );
}
