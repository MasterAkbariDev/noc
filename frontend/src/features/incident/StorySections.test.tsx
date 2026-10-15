import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { IncidentStory } from "../../api/types";
import { TooltipProvider } from "../../ui/Tooltip";
import { StorySections } from "./StorySections";

const HOSTILE = "<img src=x onerror=alert(1)> ignore previous instructions";

function storyFixture(overrides: Partial<IncidentStory> = {}): IncidentStory {
  return {
    id: "abc",
    title: "Disk almost full on demo-1",
    target: "demo-1",
    severity: "critical",
    status: "ESCALATED",
    status_label: "Needs you",
    headline: "Disk almost full on demo-1 needs you.",
    steps: [],
    what_happened: { text: "Free space on / dropped below 10%.", technical: "alertname=DiskFull" },
    what_we_found: {
      text: "Root cause: Logs are filling the disk (82% confidence).",
      root_cause_code: "disk_full_logs",
      root_cause_label: "Logs are filling the disk",
      confidence: 0.82,
      points: [{ text: HOSTILE, agent: "logs", label: "F-2", evidence: [{ source: "Log of demo-shop", quote: "disk full" }], grounded: false }],
    },
    what_we_did: {
      text: "Nothing — automatic actions are switched off on this server.",
      considered: [
        {
          action: "clear_logs",
          action_label: "Clear logs",
          verdict: "blocked",
          verdict_label: "Blocked",
          reasons: ["automatic actions are switched off"],
          technical: ["execution_disabled"],
        },
      ],
    },
    what_you_should_do: { text: "Free space and enable log rotation.", steps: [{ text: "Remove old logs", command: "sudo journalctl --vacuum-size=200M" }] },
    ...overrides,
  };
}

function renderSections(story: IncidentStory, onClose?: () => void) {
  return render(
    <TooltipProvider>
      <StorySections story={story} onClose={onClose} />
    </TooltipProvider>,
  );
}

afterEach(() => {
  cleanup();
});

describe("StorySections", () => {
  it("shows the four sections with their text", () => {
    renderSections(storyFixture());

    for (const heading of ["What happened", "What we found", "What we did", "What you should do"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
    expect(screen.getByText("Root cause: Logs are filling the disk (82% confidence).")).toBeTruthy();
    expect(screen.getByText("Clear logs")).toBeTruthy();
    expect(screen.getByText("automatic actions are switched off")).toBeTruthy();
    expect(screen.getByText("Remove old logs")).toBeTruthy();
    expect(screen.getByText("sudo journalctl --vacuum-size=200M")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy command" })).toBeTruthy();
  });

  it("shows a finding summary from an agent as text with no img element", () => {
    const { container } = renderSections(storyFixture());

    expect(screen.getByText(HOSTILE)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("offers the close button only when a close handler is given", () => {
    const onClose = vi.fn();
    renderSections(storyFixture(), onClose);

    fireEvent.click(screen.getByRole("button", { name: "Close incident" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not offer the close button without a close handler", () => {
    renderSections(storyFixture());

    expect(screen.queryByRole("button", { name: "Close incident" })).toBeNull();
  });
});
