import type {
  ActivityPage,
  FleetLive,
  LiveRange,
  ServerLive,
  ActivityVerify,
  AddLlmKeyBody,
  ApprovalDecisionBody,
  ApprovalView,
  CreateUserBody,
  IncidentDetail,
  IncidentResolutionBody,
  IncidentStory,
  IncidentSummary,
  IncidentTrace,
  LlmCheck,
  LlmConfig,
  LlmManagedKey,
  JoinCode,
  LlmProxyCheck,
  Metrics,
  EndpointView,
  PeerView,
  LlmStatus,
  MeView,
  Overview,
  Role,
  ServerDetail,
  ServerSummary,
  StreamTicket,
  SystemHealth,
  TelegramSettings,
  TelegramTest,
  TelegramUpdate,
  TotpSetup,
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

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail;
  }
  if (!Array.isArray(detail)) {
    return null;
  }
  const messages = detail.flatMap((item: unknown) =>
    typeof item === "object" && item !== null && "msg" in item && typeof item.msg === "string" ? [item.msg] : [],
  );
  return messages.length > 0 ? messages.join("; ") : null;
}

async function errorDetail(response: Response): Promise<string> {
  const fallback = `${response.status} ${response.statusText}`.trim();
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      return detailText(body.detail) ?? fallback;
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

export function apiDelete(path: string): Promise<void> {
  return apiRequest<void>("DELETE", path);
}

export const TOTP_REQUIRED_DETAIL = "authentication code required";

export function login(username: string, password: string, totp?: string): Promise<MeView> {
  const body = totp === undefined || totp === "" ? { username, password } : { username, password, totp };
  return apiPost<MeView>("/api/auth/login", body);
}

export function totpSetup(currentPassword: string): Promise<TotpSetup> {
  return apiPost<TotpSetup>("/api/auth/totp/setup", { current_password: currentPassword });
}

export function totpEnable(code: string): Promise<void> {
  return apiPost<void>("/api/auth/totp/enable", { code });
}

export function totpDisable(currentPassword: string, code: string): Promise<void> {
  return apiPost<void>("/api/auth/totp/disable", { current_password: currentPassword, code });
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

export type IncidentListQuery = {
  status?: string;
  statuses?: string[];
  q?: string;
  limit?: number;
};

export function listIncidents(query: IncidentListQuery = {}): Promise<IncidentSummary[]> {
  const params = new URLSearchParams();
  if (query.status) {
    params.set("status", query.status);
  }
  for (const status of query.statuses ?? []) {
    params.append("statuses", status);
  }
  if (query.q) {
    params.set("q", query.q);
  }
  if (query.limit !== undefined) {
    params.set("limit", String(query.limit));
  }
  const text = params.toString();
  const suffix = text === "" ? "" : `?${text}`;
  return apiGet<IncidentSummary[]>(`/api/incidents${suffix}`);
}

export function getIncident(id: string): Promise<IncidentDetail> {
  return apiGet<IncidentDetail>(`/api/incidents/${encodeURIComponent(id)}`);
}

export function getTrace(id: string): Promise<IncidentTrace> {
  return apiGet<IncidentTrace>(`/api/incidents/${encodeURIComponent(id)}/trace`);
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

export function getLlmConfig(): Promise<LlmConfig> {
  return apiGet<LlmConfig>("/api/llm/config");
}

export function addLlmKey(body: AddLlmKeyBody): Promise<LlmManagedKey> {
  return apiPost<LlmManagedKey>("/api/llm/keys", body);
}

export function revokeLlmKey(id: string): Promise<void> {
  return apiDelete(`/api/llm/keys/${encodedId(id)}`);
}

export function checkLlmKey(label: string): Promise<LlmCheck> {
  return apiPost<LlmCheck>("/api/llm/keys/check", { label });
}

export function setLlmProxy(provider: string, url: string | null): Promise<LlmConfig> {
  return apiRequest<LlmConfig>("PUT", `/api/llm/providers/${encodedId(provider)}/proxy`, { url });
}

export function resetLlmProxy(provider: string): Promise<LlmConfig> {
  return apiRequest<LlmConfig>("DELETE", `/api/llm/providers/${encodedId(provider)}/proxy`);
}

export function checkLlmProxy(provider: string): Promise<LlmCheck> {
  return apiPost<LlmCheck>(`/api/llm/providers/${encodedId(provider)}/proxy/check`, {});
}

export function checkAllLlmProxies(): Promise<LlmProxyCheck[]> {
  return apiPost<LlmProxyCheck[]>("/api/llm/proxies/check", {});
}

export function setLlmChain(tier: string, entries: string[]): Promise<LlmConfig> {
  return apiRequest<LlmConfig>("PUT", `/api/llm/chains/${encodedId(tier)}`, { entries });
}

export function resetLlmChain(tier: string): Promise<LlmConfig> {
  return apiRequest<LlmConfig>("DELETE", `/api/llm/chains/${encodedId(tier)}`);
}

export function getMetrics(days: number): Promise<Metrics> {
  return apiGet<Metrics>(`/api/metrics?days=${encodeURIComponent(String(days))}`);
}

export function getTelegram(): Promise<TelegramSettings> {
  return apiGet<TelegramSettings>("/api/notifications/telegram");
}

export function saveTelegram(body: TelegramUpdate): Promise<TelegramSettings> {
  return apiRequest<TelegramSettings>("PUT", "/api/notifications/telegram", body);
}

export function setTelegramToken(token: string): Promise<TelegramSettings> {
  return apiRequest<TelegramSettings>("PUT", "/api/notifications/telegram/token", { token });
}

export function removeTelegramToken(): Promise<TelegramSettings> {
  return apiRequest<TelegramSettings>("DELETE", "/api/notifications/telegram/token");
}

export function setTelegramProxy(url: string | null): Promise<TelegramSettings> {
  return apiRequest<TelegramSettings>("PUT", "/api/notifications/telegram/proxy", { url });
}

export function testTelegram(): Promise<TelegramTest> {
  return apiPost<TelegramTest>("/api/notifications/telegram/test", {});
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

export function deleteUser(id: string): Promise<void> {
  return apiDelete(`/api/users/${encodedId(id)}`);
}

export function resetUserPassword(id: string, newPassword: string): Promise<void> {
  return apiPost<void>(`/api/users/${encodedId(id)}/password`, { new_password: newPassword });
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

export function getFleetLive(range: LiveRange): Promise<FleetLive> {
  return apiGet<FleetLive>(`/api/live/servers?range=${encodeURIComponent(range)}`);
}

export function getServerLive(id: string, range: LiveRange): Promise<ServerLive> {
  return apiGet<ServerLive>(`/api/live/servers/${encodedId(id)}?range=${encodeURIComponent(range)}`);
}

export function getPeers(): Promise<PeerView[]> {
  return apiGet<PeerView[]>("/api/peers");
}

export function createJoinCode(name: string): Promise<JoinCode> {
  return apiPost<JoinCode>("/api/peers/join-codes", { name });
}

export function joinPeer(code: string, label: string): Promise<PeerView> {
  return apiPost<PeerView>("/api/peers/join", { code, label });
}

export function refreshPeer(id: string): Promise<PeerView> {
  return apiPost<PeerView>(`/api/peers/${encodedId(id)}/refresh`, {});
}

export function removePeer(id: string): Promise<void> {
  return apiDelete(`/api/peers/${encodedId(id)}`);
}

export function setServerAutomation(name: string, level: string): Promise<{ name: string; automation_level: string }> {
  return apiRequest("PUT", `/api/servers/${encodedId(name)}/automation`, { level });
}

export function setServerLabel(name: string, label: string | null): Promise<{ name: string; label: string | null }> {
  return apiRequest("PUT", `/api/servers/${encodedId(name)}/label`, { label });
}

export function getEndpoints(): Promise<EndpointView[]> {
  return apiGet<EndpointView[]>("/api/endpoints");
}

export function addEndpoint(body: {
  name: string;
  host: string;
  ssh_port: number;
  url: string | null;
}): Promise<EndpointView> {
  return apiPost<EndpointView>("/api/endpoints", body);
}

export function checkEndpoint(id: string): Promise<EndpointView> {
  return apiPost<EndpointView>(`/api/endpoints/${encodedId(id)}/check`, {});
}

export function removeEndpoint(id: string): Promise<void> {
  return apiDelete(`/api/endpoints/${encodedId(id)}`);
}
