import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { LlmKeyView, LlmStatus } from "../../api/types";
import { TooltipProvider } from "../../ui";
import { LlmPanel } from "./LlmPanel";

const HOSTILE_ERROR = '<img src=x onerror="alert(1)"><script>alert(2)</script>quota';

const workingKey: LlmKeyView = {
  label: "gemini#1a2b3c4d",
  provider: "gemini",
  state: "ok",
  cooling_until: null,
  last_error: null,
  last_error_at: null,
  last_success_at: "2026-10-12T10:00:00Z",
  models: [{ tier: "strong", model: "gemini-2.5-pro", used_today: 12, daily_limit: 100 }],
};

const coolingKey: LlmKeyView = {
  label: "groq#9f8e7d6c",
  provider: "groq",
  state: "cooling",
  cooling_until: "2026-10-12T12:00:00Z",
  last_error: "rate_limited",
  last_error_at: "2026-10-12T11:55:00Z",
  last_success_at: null,
  models: [],
};

function status(overrides: Partial<LlmStatus> = {}): LlmStatus {
  return { mode: "live", keys: [workingKey, coolingKey], ...overrides };
}

function renderPanel(value: LlmStatus) {
  return render(
    <TooltipProvider>
      <LlmPanel status={value} />
    </TooltipProvider>,
  );
}

function rowFor(label: string): HTMLElement {
  const rows = within(screen.getByRole("table")).getAllByRole("row");
  const row = rows.find((candidate) => candidate.textContent?.includes(label));
  if (row === undefined) {
    throw new Error(`no row for ${label}`);
  }
  return row;
}

describe("LlmPanel", () => {
  it("shows the mode badge and no replay note when the mode is live", () => {
    renderPanel(status());

    expect(screen.getByText("Live")).toBeTruthy();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("explains that replay answers are recorded when the mode is replay", () => {
    renderPanel(status({ mode: "replay" }));

    expect(screen.getByText("Replay")).toBeTruthy();
    const note = screen.getByRole("note");
    expect(note.textContent).toContain("recorded file");
  });

  it("shows each key with its provider and a plain state word", () => {
    renderPanel(status());

    const working = rowFor("gemini#1a2b3c4d");
    expect(within(working).getByText("gemini")).toBeTruthy();
    expect(within(working).getByText("Working")).toBeTruthy();

    const cooling = rowFor("groq#9f8e7d6c");
    expect(within(cooling).getByText("Cooling down")).toBeTruthy();
  });

  it("shows used against the daily limit for each model, with a bar that matches the share", () => {
    const { container } = renderPanel(status());

    expect(screen.getByText("12 of 100 used today")).toBeTruthy();
    expect(container.querySelector('[style="width: 12%;"]')).not.toBeNull();
  });

  it("shows when a cooling key may be used again", () => {
    renderPanel(status());

    const cooling = rowFor("groq#9f8e7d6c");
    expect(within(cooling).getByText(/Until/)).toBeTruthy();
    expect(cooling.querySelector("time")?.getAttribute("datetime")).toBe("2026-10-12T12:00:00Z");
  });

  it("shows the last error class as code text and the last success time", () => {
    renderPanel(status());

    const cooling = rowFor("groq#9f8e7d6c");
    expect(within(cooling).getByText("rate_limited").tagName).toBe("CODE");
    expect(within(cooling).getByText("none yet", { exact: false })).toBeTruthy();
    expect(within(rowFor("gemini#1a2b3c4d")).getByText("No error recorded")).toBeTruthy();
  });

  it("shows a hostile error text as text and creates no element from it", () => {
    const hostileKey: LlmKeyView = { ...coolingKey, last_error: HOSTILE_ERROR };
    const { container } = renderPanel(status({ keys: [hostileKey] }));

    expect(screen.getByText(HOSTILE_ERROR)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("says no keys are configured when the list is empty", () => {
    renderPanel(status({ keys: [] }));

    expect(screen.getByText("No LLM keys are configured.")).toBeTruthy();
  });
});
