import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { useSession } from "../../auth/session";
import { sessionFor } from "../settings/fixtures";
import { TooltipProvider } from "../../ui/Tooltip";
import { ServerCard } from "./ServerCard";
import { HOSTILE_TEXT, SERVER_ID, summaryFixture } from "./fixtures";

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

function asViewer() {
  vi.mocked(useSession).mockReturnValue(sessionFor({ username: "viewer", role: "viewer", via: "session" }));
}

function renderCard(overrides: Parameters<typeof summaryFixture>[0] = {}) {
  return render(
    <TooltipProvider>
      <MemoryRouter>
        <ServerCard server={summaryFixture(overrides)} />
      </MemoryRouter>
    </TooltipProvider>,
  );
}

afterEach(() => {
  cleanup();
});

describe("ServerCard", () => {
  beforeEach(asViewer);

  it("shows the HALTED badge only when automation is halted", () => {
    const { unmount } = renderCard();
    expect(screen.queryByText("Halted")).toBeNull();
    unmount();

    renderCard({ halted: true });
    expect(screen.getByText("Halted")).toBeTruthy();
  });

  it("highlights the prod environment and leaves other environments plain", () => {
    const { unmount } = renderCard({ environment: "prod" });
    expect(screen.getByText("prod").className).toContain("bg-warning-soft");
    unmount();

    renderCard({ environment: "staging" });
    expect(screen.getByText("staging").className).not.toContain("bg-warning-soft");
  });

  it("links the name to the server page", () => {
    renderCard();

    expect(screen.getByRole("link", { name: "web-1" }).getAttribute("href")).toBe(`/servers/${SERVER_ID}`);
  });

  it("shows the headline, the status label and the open incidents as text", () => {
    renderCard();

    expect(screen.getByText("Disk 92% full")).toBeTruthy();
    expect(screen.getByText("Reachable")).toBeTruthy();
    expect(screen.getByText("1 open incident")).toBeTruthy();
    expect(screen.getByText("Critical")).toBeTruthy();
  });

  it("names the open incidents once, in the footer, not in the headline", () => {
    renderCard();

    expect(screen.queryByText("Disk 92% full · 1 open incident")).toBeNull();
    expect(screen.getAllByText(/open incident/)).toHaveLength(1);
  });

  it("leaves out the headline line when it only repeats the open incidents", () => {
    renderCard({ headline: "1 open incident" });

    expect(screen.getAllByText("1 open incident")).toHaveLength(1);
  });

  it("shows the automation label, with the raw level in a tooltip term", () => {
    renderCard();

    expect(screen.getByText("Safe fixes run automatically").getAttribute("tabindex")).toBe("0");
  });

  it("shows a hostile server name and headline as text and creates no image element", () => {
    const { container } = renderCard({ name: HOSTILE_TEXT, headline: HOSTILE_TEXT });

    expect(screen.getByRole("link", { name: HOSTILE_TEXT })).toBeTruthy();
    expect(screen.getAllByText(HOSTILE_TEXT).length).toBeGreaterThan(0);
    expect(container.querySelector("img")).toBeNull();
  });
});
