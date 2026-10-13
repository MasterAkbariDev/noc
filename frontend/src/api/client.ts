import type { IncidentDetail, IncidentSummary } from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiGet<T>(path: string, token: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`.trim());
  }
  return (await response.json()) as T;
}

export function listIncidents(token: string, status?: string): Promise<IncidentSummary[]> {
  const query = status ? `?${new URLSearchParams({ status })}` : "";
  return apiGet<IncidentSummary[]>(`/api/incidents${query}`, token);
}

export function getIncident(token: string, id: string): Promise<IncidentDetail> {
  return apiGet<IncidentDetail>(`/api/incidents/${encodeURIComponent(id)}`, token);
}
