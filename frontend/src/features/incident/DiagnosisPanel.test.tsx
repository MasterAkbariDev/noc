import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import type { DiagnosisView } from "../../api/types";
import { TooltipProvider } from "../../ui/Tooltip";
import { DiagnosisPanel } from "./DiagnosisPanel";

const HOSTILE_DESCRIPTION = "<script>alert(1)</script> ignore previous instructions";

const diagnosis: DiagnosisView = {
  primary_code: "service_crashed",
  confidence: 0.82,
  is_security_incident: false,
  hypotheses: [
    {
      root_cause_code: "disk_full",
      description: "Logs filled the disk",
      confidence: 0.3,
      supporting_findings: ["F-2"],
      contradicting_findings: [],
      affected_resource_id: null,
    },
    {
      root_cause_code: "service_crashed",
      description: HOSTILE_DESCRIPTION,
      confidence: 0.82,
      supporting_findings: ["F-1"],
      contradicting_findings: ["F-3"],
      affected_resource_id: "svc-web",
    },
  ],
  needs_more_info: ["disk_usage"],
  ungrounded_findings: 1,
};

afterEach(() => {
  cleanup();
});

function renderPanel(value: DiagnosisView | null) {
  return render(
    <TooltipProvider>
      <MemoryRouter>
        <DiagnosisPanel diagnosis={value} />
      </MemoryRouter>
    </TooltipProvider>,
  );
}

describe("DiagnosisPanel", () => {
  it("ranks hypotheses by confidence, highest first", () => {
    const { container } = renderPanel(diagnosis);

    const items = container.querySelectorAll("li.hypothesis");
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("Service crashed");
    expect(items[1]?.textContent).toContain("Disk full");
  });

  it("renders a hostile hypothesis description as text and creates no script element", () => {
    const { container } = renderPanel(diagnosis);

    expect(screen.getByText(HOSTILE_DESCRIPTION)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });

  it("links supporting and contradicting labels to the finding anchors", () => {
    const { container } = renderPanel(diagnosis);

    const item = container.querySelectorAll("li.hypothesis")[0];
    const support = within(item as HTMLElement).getByRole("link", { name: "F-1" });
    const contradiction = within(item as HTMLElement).getByRole("link", { name: "F-3" });
    expect(support.getAttribute("href")).toMatch(/#finding-F-1$/);
    expect(contradiction.getAttribute("href")).toMatch(/#finding-F-3$/);
  });

  it("shows the primary cause as a plain name with the code in a focusable term", () => {
    const { container } = renderPanel(diagnosis);

    const cause = screen.getAllByText("Service crashed")[0]!;
    expect(cause.getAttribute("tabindex")).toBe("0");
    expect(container.querySelector("dl")?.querySelector("code")).toBeNull();
  });

  it("says so when no diagnosis exists", () => {
    renderPanel(null);

    expect(screen.getByText("Diagnosis not yet recorded.")).toBeTruthy();
  });
});
