import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ToolCallView } from "../api/types";
import { ToolCallsTable } from "./ToolCallsTable";

const HOSTILE_ARG = '<img src=x onerror=alert(1)>';

const calls: ToolCallView[] = [
  {
    ref: "M1",
    agent: "metrics",
    tool: "prom_query",
    args: { query: "up" },
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
  it("groups the calls under a heading per agent", () => {
    render(<ToolCallsTable calls={calls} />);

    const headings = screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
    expect(headings).toEqual(["metrics", "logs"]);
    const metricsTable = screen.getAllByRole("table")[0]!;
    expect(within(metricsTable).getByText("prom_query")).toBeTruthy();
  });

  it("shows ok for a successful call and denied for a denied one", () => {
    render(<ToolCallsTable calls={calls} />);

    expect(screen.getByText("ok").className).toContain("badge-ok");
    const denied = screen.getByText("denied");
    expect(denied.className).toContain("badge-danger");
    expect(screen.getByText("unit not on allow-list")).toBeTruthy();
  });

  it("lists the injection flags in a badge", () => {
    render(<ToolCallsTable calls={calls} />);

    const badge = screen.getByText("injection flags: role_override, tool_request");
    expect(badge.className).toContain("badge-danger");
  });

  it("shows the args as JSON text and creates no img element for a hostile arg", () => {
    const { container } = render(<ToolCallsTable calls={calls} />);

    expect(screen.getByText(JSON.stringify({ unit: HOSTILE_ARG }))).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("says so when there are no tool calls", () => {
    render(<ToolCallsTable calls={[]} />);

    expect(screen.getByText("No tool calls recorded.")).toBeTruthy();
  });
});
