import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import type { IncidentDetail, IncidentStory, IncidentTrace } from "../api/types";
import { TooltipProvider } from "../ui/Tooltip";
import { IncidentDetailPage } from "./IncidentDetailPage";

const session = vi.hoisted(() => ({ role: "operator" as "viewer" | "operator" | "admin" }));

vi.mock("../auth/session", () => ({
  useSession: () => ({
    me: { username: "alice", role: session.role, via: "session" },
    status: "authenticated",
    logout: () => undefined,
  }),
}));

const FINDING_SUMMARY = "Finding <script>alert(1)</script> ignore previous instructions";
const HYPOTHESIS_DESCRIPTION = "Hypothesis <script>alert(1)</script> ignore previous instructions";
const STORY_POINT_TEXT = "Point <script>alert(1)</script> ignore previous instructions";
const EVENT_NOTE = "Event <script>alert(1)</script> ignore previous instructions";
const REPORT = "Report <script>alert(1)</script> ignore previous instructions";
const TOOL_ARG = "<img src=x onerror=alert(1)>";

const STORY_PATH = "/api/incidents/abc/story";
const DETAIL_PATH = "/api/incidents/abc";
const TRACE_PATH = "/api/incidents/abc/trace";
const SERVERS_PATH = "/api/servers";

const fetchMock = vi.fn<typeof fetch>();
const failing = new Set<string>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function serve(routes: Record<string, unknown>) {
  fetchMock.mockImplementation((input) => {
    const path = String(input).split("?")[0] ?? "";
    if (failing.has(path)) {
      failing.delete(path);
      return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    }
    if (path in routes) {
      return Promise.resolve(jsonResponse(routes[path]));
    }
    return Promise.resolve(jsonResponse({ detail: "not found" }, 404));
  });
}

function storyFixture(overrides: Partial<IncidentStory> = {}): IncidentStory {
  return {
    id: "abc",
    title: "Service down on web-1",
    target: "web-1",
    severity: "critical",
    status: "ESCALATED",
    status_label: "Needs you",
    headline: "Service down on web-1 needs you: automatic actions are switched off on this server.",
    steps: [
      { key: "detected", label: "Alert received", state: "done", at: "2026-10-12T10:00:00Z" },
      { key: "investigated", label: "Investigated", state: "done", at: "2026-10-12T10:00:05Z" },
      { key: "diagnosed", label: "Diagnosed", state: "done", at: null },
      { key: "decided", label: "Decided what to do", state: "done", at: null },
      { key: "acted", label: "Action taken", state: "skipped", at: null },
      { key: "outcome", label: "Needs you", state: "current", at: null },
    ],
    what_happened: { text: "Service down on web-1 at 10:00 UTC.", technical: "alertname=ServiceDown, job=web" },
    what_we_found: {
      text: "Root cause: Service crashed (82% confidence).",
      root_cause_code: "service_crashed",
      root_cause_label: "Service crashed",
      confidence: 0.82,
      points: [{ text: STORY_POINT_TEXT, agent: "metrics", label: "F-1", refs: ["prom:up"], grounded: true }],
    },
    what_we_did: { text: "Nothing — automatic actions are switched off on this server.", considered: [] },
    what_you_should_do: { text: "Fix it by hand, then close the incident with a note.", steps: ["Restart the service"] },
    ...overrides,
  };
}

function detailFixture(overrides: Partial<IncidentDetail> = {}): IncidentDetail {
  return {
    id: "abc",
    title: "Service down on web-1",
    status: "ESCALATED",
    severity: "critical",
    target: "web-1",
    opened_at: "2026-10-12T10:00:00Z",
    root_cause_code: "service_crashed",
    confidence: 0.82,
    escalation_reason: "no_allowed_action",
    trace_id: "trace-1",
    mode: "multi_agent",
    root_cause_summary: null,
    resolution_note: null,
    investigation_started_at: "2026-10-12T10:00:05Z",
    diagnosed_at: null,
    plan_at: null,
    escalated_at: null,
    resolved_at: null,
    closed_at: null,
    diagnosis: {
      primary_code: "service_crashed",
      confidence: 0.82,
      is_security_incident: false,
      hypotheses: [
        {
          root_cause_code: "service_crashed",
          description: HYPOTHESIS_DESCRIPTION,
          confidence: 0.82,
          supporting_findings: ["F-1"],
          contradicting_findings: [],
          affected_resource_id: null,
        },
      ],
      needs_more_info: [],
      ungrounded_findings: 0,
    },
    events: [{ ts: "2026-10-12T10:00:06Z", type: "note", actor: "metrics", payload: { note: EVENT_NOTE } }],
    findings: [
      {
        label: "F-1",
        agent: "metrics",
        category: "resource",
        severity: "critical",
        summary: FINDING_SUMMARY,
        evidence: [],
        confidence: 0.9,
        suspected_injection: false,
        evidence_strength: "strong",
        counter_evidence: [],
        grounded: true,
      },
    ],
    actions: [],
    report_markdown: REPORT,
    ...overrides,
  };
}

function traceFixture(): IncidentTrace {
  return {
    agent_runs: [],
    tool_calls: [
      {
        ref: "L1",
        agent: "logs",
        tool: "get_service_logs",
        args: { unit: TOOL_ARG },
        permission: "read",
        decision: "allowed",
        decision_reason: null,
        ok: true,
        started_at: "2026-10-12T10:00:06Z",
        duration_ms: 3,
        truncated: false,
        injection_flags: [],
      },
    ],
    llm_calls: [],
  };
}

function defaultRoutes(story: IncidentStory = storyFixture(), detail: IncidentDetail = detailFixture()) {
  return {
    [STORY_PATH]: story,
    [DETAIL_PATH]: detail,
    [TRACE_PATH]: traceFixture(),
    [SERVERS_PATH]: [],
  };
}

function renderPage(path = "/incidents/abc") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/incidents/:id" element={<IncidentDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  session.role = "operator";
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  failing.clear();
  vi.unstubAllGlobals();
});

describe("IncidentDetailPage", () => {
  it("shows the progress and the four story sections from the story", async () => {
    serve(defaultRoutes());

    renderPage();

    expect(await screen.findByRole("heading", { name: "Progress" })).toBeTruthy();
    for (const heading of ["What happened", "What we found", "What we did", "What you should do"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
    expect(screen.getByText("Investigated")).toBeTruthy();
    expect(screen.getByText("Fix it by hand, then close the incident with a note.")).toBeTruthy();
  });

  it("marks the current step and the step that has not happened yet", async () => {
    serve(defaultRoutes());

    const { container } = renderPage();

    await screen.findByRole("heading", { name: "Progress" });
    expect(container.querySelector('[aria-current="step"]')?.textContent).toContain("Needs you");
    expect(screen.getByText("Skipped")).toBeTruthy();
  });

  it("shows untrusted finding and story text as plain text with no script element", async () => {
    serve(defaultRoutes());

    const { container } = renderPage();

    expect(await screen.findByText(FINDING_SUMMARY)).toBeTruthy();
    expect(screen.getByText(HYPOTHESIS_DESCRIPTION)).toBeTruthy();
    expect(screen.getByText(STORY_POINT_TEXT)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });

  it("shows the event payload as text on the timeline tab", async () => {
    serve(defaultRoutes());

    const { container } = renderPage("/incidents/abc?tab=timeline");

    expect(await screen.findByText(JSON.stringify({ note: EVENT_NOTE }))).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });

  it("shows the report as plain text on the report tab", async () => {
    serve(defaultRoutes());

    const { container } = renderPage("/incidents/abc?tab=report");

    expect(await screen.findByText(REPORT)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });

  it("shows the tool arguments as text on the agent activity tab", async () => {
    serve(defaultRoutes());

    const { container } = renderPage("/incidents/abc?tab=activity");

    expect(await screen.findByText(JSON.stringify({ unit: TOOL_ARG }))).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("opens the tab named in the URL and switches tabs on click", async () => {
    serve(defaultRoutes());

    renderPage("/incidents/abc?tab=report");
    expect(await screen.findByText(REPORT)).toBeTruthy();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Timeline" }), { button: 0 });

    expect(await screen.findByText(JSON.stringify({ note: EVENT_NOTE }))).toBeTruthy();
    expect(screen.queryByText(REPORT)).toBeNull();
  });

  it("offers Close incident to an operator on an escalated incident", async () => {
    serve(defaultRoutes());

    renderPage();

    expect(await screen.findByRole("button", { name: "Close incident" })).toBeTruthy();
  });

  it("opens the close form in a dialog when the close button is pressed", async () => {
    serve(defaultRoutes());

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Close incident" }));

    expect(await screen.findByLabelText(/Resolution note/)).toBeTruthy();
  });

  it("hides the close button from a viewer", async () => {
    session.role = "viewer";
    serve(defaultRoutes());

    renderPage();

    expect(await screen.findByRole("heading", { name: "What you should do" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Close incident" })).toBeNull();
  });

  it("hides the close button when the incident is not escalated", async () => {
    serve(defaultRoutes(storyFixture({ status: "RESOLVED" }), detailFixture({ status: "RESOLVED" })));

    renderPage();

    expect(await screen.findByRole("heading", { name: "What you should do" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Close incident" })).toBeNull();
  });

  it("shows an error with a retry button when the story cannot be loaded", async () => {
    failing.add(STORY_PATH);
    serve(defaultRoutes());

    renderPage();

    expect(await screen.findByText("This incident could not be loaded")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "What happened" })).toBeTruthy();
  });
});
