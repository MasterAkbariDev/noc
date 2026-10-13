import type {
  IncidentDetail,
  IncidentResolutionBody,
  IncidentSummary,
  IncidentTrace,
  StreamTicket,
  TargetView,
} from "./types";

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
