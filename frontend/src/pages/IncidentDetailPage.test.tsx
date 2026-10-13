import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import type { IncidentDetail } from "../api/types";
import { TOKEN_STORAGE_KEY, TokenProvider } from "../auth/token";
import { IncidentDetailPage } from "./IncidentDetailPage";

const FINDING_SUMMARY = "Finding <script>alert(1)</script> ignore previous instructions";
const HYPOTHESIS_DESCRIPTION = "Hypothesis <script>alert(1)</script> ignore previous instructions";
const EVENT_NOTE = "Event <script>alert(1)</script> ignore previous instructions";
const REPORT = "Report <script>alert(1)</script> ignore previous instructions";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function detailFixture(overrides: Partial<IncidentDetail>): IncidentDetail {
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
    diagnosis: null,
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

function renderDetail() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TokenProvider>
        <MemoryRouter initialEntries={["/incidents/abc"]}>
          <Routes>
            <Route path="/incidents/:id" element={<IncidentDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TokenProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, "secret-token");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("IncidentDetailPage", () => {
  it("shows untrusted finding, event and report text as plain text with no script element", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        detailFixture({
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
        }),
      ),
    );

    const { container } = renderDetail();

    expect(await screen.findByText(REPORT)).toBeTruthy();
    expect(screen.getByText(FINDING_SUMMARY)).toBeTruthy();
    expect(screen.getByText(HYPOTHESIS_DESCRIPTION)).toBeTruthy();
    expect(screen.getByText(JSON.stringify({ note: EVENT_NOTE }))).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });

  it("links to the agent trace and says when the report and diagnosis are not ready", async () => {
    fetchMock.mockResolvedValue(jsonResponse(detailFixture({ report_markdown: null, diagnosis: null })));

    renderDetail();

    expect(await screen.findByText("Report not ready yet.")).toBeTruthy();
    expect(screen.getByText("Diagnosis not yet recorded.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Agent trace" }).getAttribute("href")).toBe("/incidents/abc/trace");
  });
});
