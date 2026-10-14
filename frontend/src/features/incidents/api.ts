import { listIncidents } from "../../api/client";
import type { IncidentSummary } from "../../api/types";
import { statusesFor, type IncidentFilter } from "./filters";

export const ALL_INCIDENTS_LIMIT = 200;

export function listIncidentRows(filter: IncidentFilter, search: string): Promise<IncidentSummary[]> {
  return listIncidents({ statuses: statusesFor(filter), q: search, limit: ALL_INCIDENTS_LIMIT });
}
