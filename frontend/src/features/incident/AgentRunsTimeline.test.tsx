import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { AgentRunView } from "../../api/types";
import { AgentRunsTimeline, timelineBars } from "./AgentRunsTimeline";

const HOSTILE_ERROR = '<img src=x onerror=alert(1)>Logs unavailable';

const runs: AgentRunView[] = [
  {
    id: "run-metrics",
    agent: "metrics",
    status: "succeeded",
    started_at: "2026-10-12T10:00:00Z",
    ended_at: "2026-10-12T10:00:10Z",
    rounds: 2,
    llm_calls: 2,
    tool_calls: 3,
    error: null,
  },
  {
    id: "run-logs",
    agent: "logs",
    status: "failed",
    started_at: "2026-10-12T10:00:05Z",
    ended_at: "2026-10-12T10:00:20Z",
    rounds: 1,
    llm_calls: 1,
    tool_calls: 1,
    error: HOSTILE_ERROR,
  },
];

afterEach(() => {
  cleanup();
});

function barFor(container: HTMLElement, runId: string): HTMLElement {
  const bar = container.querySelector(`li:nth-child(${runs.findIndex((run) => run.id === runId) + 1}) .timeline-bar`);
  if (!(bar instanceof HTMLElement)) {
    throw new Error(`no bar for ${runId}`);
  }
  return bar;
}

describe("AgentRunsTimeline", () => {
  it("draws one bar per run with the agent, status and counts", () => {
    const { container } = render(<AgentRunsTimeline runs={runs} />);

    expect(container.querySelectorAll(".timeline-bar")).toHaveLength(2);
    expect(screen.getByText("Metrics specialist")).toBeTruthy();
    expect(screen.getByText("finished")).toBeTruthy();
    expect(screen.getByText("started after 0.0 s · worked 10 s · 3 checks · 2 AI calls")).toBeTruthy();
    expect(screen.getByText("started after 5.0 s · worked 15 s · 1 check · 1 AI call")).toBeTruthy();
    expect(screen.getByText("20 s")).toBeTruthy();
  });

  it("places parallel runs on a shared axis so they overlap", () => {
    const { container } = render(<AgentRunsTimeline runs={runs} />);

    const metrics = barFor(container, "run-metrics");
    const logs = barFor(container, "run-logs");
    const metricsEnd = parseFloat(metrics.style.getPropertyValue("--bar-left")) + parseFloat(metrics.style.getPropertyValue("--bar-width"));
    expect(parseFloat(logs.style.getPropertyValue("--bar-left"))).toBeLessThan(metricsEnd);
    expect(parseFloat(metrics.style.getPropertyValue("--bar-left"))).toBe(0);
    expect(parseFloat(logs.style.getPropertyValue("--bar-left"))).toBeCloseTo(25, 5);
  });

  it("shows a hostile error as text and creates no img element", () => {
    const { container } = render(<AgentRunsTimeline runs={runs} />);

    expect(screen.getByText(HOSTILE_ERROR)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("says so when there are no runs", () => {
    render(<AgentRunsTimeline runs={[]} />);

    expect(screen.getByText("No agent runs recorded.")).toBeTruthy();
  });
});

describe("timelineBars", () => {
  it("extends a run that has not ended to the end of the axis", () => {
    const running: AgentRunView = { ...runs[0]!, id: "run-running", status: "running", ended_at: null };

    const bars = timelineBars([runs[0]!, running]);

    const runningBar = bars.find((bar) => bar.run.id === "run-running");
    expect(runningBar?.left).toBe(0);
    expect(runningBar?.width).toBe(100);
  });

  it("gives a zero-length run a visible width", () => {
    const instant: AgentRunView = { ...runs[0]!, id: "run-instant", ended_at: runs[0]!.started_at };

    const bars = timelineBars([runs[0]!, instant]);

    expect(bars.find((bar) => bar.run.id === "run-instant")?.width).toBeGreaterThan(0);
  });
});
