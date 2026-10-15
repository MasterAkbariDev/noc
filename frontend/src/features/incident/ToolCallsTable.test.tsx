import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ToolCallView } from "../../api/types";
import { ToolCallsTable } from "./ToolCallsTable";

const HOSTILE_ARG = '<img src=x onerror=alert(1)>';

const calls: ToolCallView[] = [
  {
    ref: "M1",
    agent: "metrics",
    tool: "prom_query",
    args: { query: "up" },
    description: "History of up, last 1h",
    permission: "read",
    decision: "allowed",
    decision_reason: null,
    ok: true,
    started_at: "2026-10-12T10:00:01Z",
    duration_ms: 42,
    truncated: false,
    injection_flags: [],
  },
  {
    ref: "L1",
    agent: "logs",
    tool: "get_service_logs",
    args: { unit: HOSTILE_ARG },
    description: "Log of demo-shop, last 30 minutes",
    permission: "read",
    decision: "denied",
    decision_reason: "unit not on allow-list",
    ok: false,
    started_at: "2026-10-12T10:00:06Z",
    duration_ms: 3,
    truncated: true,
    injection_flags: ["role_override", "tool_request"],
  },
];

afterEach(() => {
  cleanup();
});

describe("ToolCallsTable", () => {
  it("groups the checks under a heading per specialist and describes each in words", () => {
    render(<ToolCallsTable calls={calls} />);

    const headings = screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
    expect(headings).toEqual(["Metrics specialist", "Logs specialist"]);
    const metricsTable = screen.getAllByRole("table")[0]!;
    expect(within(metricsTable).getByText("History of up, last 1h")).toBeTruthy();
  });

  it("shows answered for a successful call and not allowed for a denied one", () => {
    render(<ToolCallsTable calls={calls} />);

    expect(screen.getByText("answered").className).toContain("text-ok");
    const denied = screen.getByText("not allowed");
    expect(denied.className).toContain("text-critical");
    expect(screen.getByText("unit not on allow-list")).toBeTruthy();
  });

  it("warns in words when the answer tried to steer the AI", () => {
    render(<ToolCallsTable calls={calls} />);

    const badge = screen.getByText("the answer contained text that tries to steer the AI");
    expect(badge.className).toContain("text-critical");
  });

  it("keeps the raw arguments as text under technical details, with no img element", () => {
    const { container } = render(<ToolCallsTable calls={calls} />);

    expect(screen.getByText(JSON.stringify({ unit: HOSTILE_ARG }))).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("says so when there are no tool calls", () => {
    render(<ToolCallsTable calls={[]} />);

    expect(screen.getByText("No checks were made on the server.")).toBeTruthy();
  });
});
