import { apiGet } from "../../api/client";
import type { IncidentSummary } from "../../api/types";

export const ALL_INCIDENTS_LIMIT = 200;

export function listAllIncidents(): Promise<IncidentSummary[]> {
  const query = new URLSearchParams({ limit: String(ALL_INCIDENTS_LIMIT) });
  return apiGet<IncidentSummary[]>(`/api/incidents?${query}`);
}
