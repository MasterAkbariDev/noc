import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { LlmCallView } from "../../api/types";
import { LlmCallsTable, sumTokens, sumWaitMs } from "./LlmCallsTable";

const HOSTILE_ERROR = '<img src=x onerror=alert(1)>Provider timeout';

const calls: LlmCallView[] = [
  {
    id: "call-1",
    agent: "metrics",
    tier: "small",
    provider: "gemini",
    model: "flash-lite",
    mode: "json",
    tokens_in: 300,
    tokens_out: 40,
    latency_ms: 820,
    wait_ms: 150,
    fallback: false,
    finish_reason: "stop",
    redactions: 0,
    error: null,
    created_at: "2026-10-12T10:00:02Z",
  },
  {
    id: "call-2",
    agent: "logs",
    tier: "small",
    provider: "groq",
    model: "llama-small",
    mode: "json",
    tokens_in: 500,
    tokens_out: 60,
    latency_ms: 1200,
    wait_ms: 350,
    fallback: true,
    finish_reason: null,
    redactions: 2,
    error: HOSTILE_ERROR,
    created_at: "2026-10-12T10:00:07Z",
  },
];

afterEach(() => {
  cleanup();
});

describe("LlmCallsTable", () => {
  it("shows a fallback badge only for the fallback call", () => {
    render(<LlmCallsTable calls={calls} />);

    const badges = screen.getAllByText("the first-choice model was busy, a backup answered");
    expect(badges).toHaveLength(1);
    expect(badges[0]?.className).toContain("text-warning");
  });

  it("shows the provider and model of each call", () => {
    render(<LlmCallsTable calls={calls} />);

    expect(screen.getByText(/gemini, /)).toBeTruthy();
    expect(screen.getByText(/llama-small/)).toBeTruthy();
  });

  it("totals the calls, tokens and waiting time in the footer", () => {
    const { container } = render(<LlmCallsTable calls={calls} />);

    expect(sumTokens(calls)).toBe(900);
    expect(sumWaitMs(calls)).toBe(500);
    const footer = container.querySelector("tfoot");
    expect(footer?.textContent).toContain("2 calls");
    expect(footer?.textContent).toContain("900 tokens");
    expect(footer?.textContent).toContain("waited 500 ms in total");
  });

  it("shows a hostile error as text and creates no img element", () => {
    const { container } = render(<LlmCallsTable calls={calls} />);

    expect(screen.getByText(HOSTILE_ERROR)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("says so when there are no AI model calls", () => {
    render(<LlmCallsTable calls={[]} />);

    expect(screen.getByText("No AI model calls were made.")).toBeTruthy();
  });
});
