import type {
  ActivityPage,
  ActivityVerify,
  CreateUserBody,
  IncidentDetail,
  IncidentResolutionBody,
  IncidentStory,
  IncidentSummary,
  IncidentTrace,
  LlmStatus,
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

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiRequest<T>(method: string, path: string, token: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}`, Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`.trim());
  }
  return (await response.json()) as T;
}

export function apiGet<T>(path: string, token: string): Promise<T> {
  return apiRequest<T>("GET", path, token);
}

export function apiPost<T>(path: string, token: string, body: unknown): Promise<T> {
  return apiRequest<T>("POST", path, token, body);
}

export function listIncidents(token: string, status?: string): Promise<IncidentSummary[]> {
  const query = status ? `?${new URLSearchParams({ status })}` : "";
  return apiGet<IncidentSummary[]>(`/api/incidents${query}`, token);
}

export function getIncident(token: string, id: string): Promise<IncidentDetail> {
  return apiGet<IncidentDetail>(`/api/incidents/${encodeURIComponent(id)}`, token);
}

export function getTrace(token: string, id: string): Promise<IncidentTrace> {
  return apiGet<IncidentTrace>(`/api/incidents/${encodeURIComponent(id)}/trace`, token);
}

export function getTargets(token: string): Promise<TargetView[]> {
  return apiGet<TargetView[]>("/api/targets", token);
}

export function closeIncident(
  token: string,
  id: string,
  body: IncidentResolutionBody,
): Promise<IncidentSummary> {
  return apiPost<IncidentSummary>(`/api/incidents/${encodeURIComponent(id)}/close`, token, body);
}

export async function fetchStreamTicket(token: string): Promise<string> {
  const issued = await apiPost<StreamTicket>("/api/events/ticket", token, {});
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

export function getOverview(token: string): Promise<Overview> {
  return apiGet<Overview>("/api/overview", token);
}

export function getSystemHealth(token: string): Promise<SystemHealth> {
  return apiGet<SystemHealth>("/api/system/health", token);
}

export function getLlmStatus(token: string): Promise<LlmStatus> {
  return apiGet<LlmStatus>("/api/system/llm", token);
}

export function getStory(token: string, id: string): Promise<IncidentStory> {
  return apiGet<IncidentStory>(`/api/incidents/${encodedId(id)}/story`, token);
}

export function getServers(token: string): Promise<ServerSummary[]> {
  return apiGet<ServerSummary[]>("/api/servers", token);
}

export function getServer(token: string, id: string): Promise<ServerDetail> {
  return apiGet<ServerDetail>(`/api/servers/${encodedId(id)}`, token);
}

export function getActivity(token: string, query: ActivityQuery = {}): Promise<ActivityPage> {
  return apiGet<ActivityPage>(`/api/activity${queryString(query)}`, token);
}

export function verifyActivity(token: string): Promise<ActivityVerify> {
  return apiGet<ActivityVerify>("/api/activity/verify", token);
}

export function getUsers(token: string): Promise<UserView[]> {
  return apiGet<UserView[]>("/api/users", token);
}

export function createUser(token: string, body: CreateUserBody): Promise<UserView> {
  return apiPost<UserView>("/api/users", token, body);
}

export function setUserRole(token: string, id: string, role: Role): Promise<UserView> {
  return apiPost<UserView>(`/api/users/${encodedId(id)}/role`, token, { role });
}

export function disableUser(token: string, id: string): Promise<UserView> {
  return apiPost<UserView>(`/api/users/${encodedId(id)}/disable`, token, {});
}

export function enableUser(token: string, id: string): Promise<UserView> {
  return apiPost<UserView>(`/api/users/${encodedId(id)}/enable`, token, {});
}

export function resetUserPassword(token: string, id: string, newPassword: string): Promise<UserView> {
  return apiPost<UserView>(`/api/users/${encodedId(id)}/password`, token, { new_password: newPassword });
}
