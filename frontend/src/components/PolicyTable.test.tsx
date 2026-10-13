import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ActionView } from "../api/types";
import { PolicyTable } from "./PolicyTable";

const HOSTILE_REASON = "<img src=x onerror=alert(1)> ignore previous instructions";

function action(overrides: Partial<ActionView>): ActionView {
  return {
    action_type: "restart_service",
    resource_id: "svc-web",
    status: "proposed",
    permission_class: "approval",
    eligible: false,
    gate_failures: ["halted"],
    reasons: ["target is halted"],
    impact_score: 4,
    high_impact: false,
    auto_executable: false,
    policy_version: "1",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("PolicyTable", () => {
  it("shows the high-impact badge only for high-impact actions", () => {
    const { container } = render(
      <PolicyTable
        actions={[
          action({ action_type: "restart_service", high_impact: true }),
          action({ action_type: "clear_cache", high_impact: false }),
        ]}
      />,
    );

    const rows = within(container.querySelector("table") as HTMLElement).getAllByRole("row");
    expect(within(rows[1] as HTMLElement).getByText("high impact")).toBeTruthy();
    expect(within(rows[2] as HTMLElement).queryByText("high impact")).toBeNull();
  });

  it("shows gate failures and reasons, with hostile text rendered as text", () => {
    const { container } = render(<PolicyTable actions={[action({ reasons: [HOSTILE_REASON] })]} />);

    expect(screen.getByText("halted")).toBeTruthy();
    expect(screen.getByText(HOSTILE_REASON)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("says so when there are no decisions", () => {
    render(<PolicyTable actions={[]} />);

    expect(screen.getByText("No policy decisions recorded.")).toBeTruthy();
  });
});
