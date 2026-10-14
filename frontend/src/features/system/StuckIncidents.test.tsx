import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import type { StuckIncident } from "../../api/types";
import { TooltipProvider } from "../../ui";
import { StuckIncidents } from "./StuckIncidents";

const HOSTILE_ERROR = '<img src=x onerror="alert(1)"><script>alert(2)</script>disk full';

const stuck: StuckIncident = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Disk almost full on web-1",
  target: "web-1",
  status: "REMEDIATING",
  since: "2026-10-12T10:00:00Z",
  job_status: "failed",
  job_attempts: 3,
  job_last_error: "sentinel refused: timeout after 30 s",
};

function renderStuck(incidents: StuckIncident[]) {
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <StuckIncidents incidents={incidents} />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

describe("StuckIncidents", () => {
  it("says None when no incident is stuck", () => {
    renderStuck([]);

    expect(screen.getByText(/^None\./)).toBeTruthy();
  });

  it("links each stuck incident title to its detail page", () => {
    renderStuck([stuck]);

    const link = screen.getByRole("link", { name: "Disk almost full on web-1" });
    expect(link.getAttribute("href")).toBe("/incidents/11111111-1111-1111-1111-111111111111");
  });

  it("shows the status word, the target and the time it has been waiting", () => {
    const { container } = renderStuck([stuck]);

    expect(screen.getByText("Taking action")).toBeTruthy();
    expect(screen.getByText(/no change since/)).toBeTruthy();
    expect(container.querySelector("time")?.getAttribute("datetime")).toBe("2026-10-12T10:00:00Z");
  });

  it("shows the job status and attempts, and the job error in a code block", () => {
    renderStuck([stuck]);

    expect(screen.getByText("failed").tagName).toBe("CODE");
    expect(screen.getByText(/attempt 3/)).toBeTruthy();
    expect(screen.getByText("sentinel refused: timeout after 30 s").tagName).toBe("CODE");
  });

  it("says no job exists when the incident has none", () => {
    renderStuck([{ ...stuck, job_status: null, job_attempts: null, job_last_error: null }]);

    expect(screen.getByText("none")).toBeTruthy();
    expect(screen.queryByText(/attempt/)).toBeNull();
  });

  it("shows a hostile job error as text and creates no element from it", () => {
    const { container } = renderStuck([{ ...stuck, job_last_error: HOSTILE_ERROR }]);

    expect(screen.getByText(HOSTILE_ERROR).tagName).toBe("CODE");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});
