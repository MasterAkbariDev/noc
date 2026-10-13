import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { NAV_ITEMS, Sidebar } from "./Sidebar";

function renderSidebar(path: string, onClose = vi.fn()) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar open={false} onClose={onClose} />
    </MemoryRouter>,
  );
  return onClose;
}

afterEach(() => {
  cleanup();
});

describe("Sidebar", () => {
  it("links to every top-level page", () => {
    renderSidebar("/");

    for (const item of NAV_ITEMS) {
      expect(screen.getByRole("link", { name: item.label }).getAttribute("href")).toBe(item.to);
    }
  });

  it("marks the current page with aria-current", () => {
    renderSidebar("/servers/abc");

    expect(screen.getByRole("link", { name: "Servers" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Overview" }).getAttribute("aria-current")).toBeNull();
  });

  it("keeps Overview active only on the root page", () => {
    renderSidebar("/incidents/abc");

    expect(screen.getByRole("link", { name: "Incidents" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Overview" }).getAttribute("aria-current")).toBeNull();
  });

  it("closes the menu when a link is chosen", () => {
    const onClose = renderSidebar("/");

    fireEvent.click(screen.getByRole("link", { name: "Activity" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes the menu from its close button", () => {
    const onClose = renderSidebar("/");

    fireEvent.click(screen.getByRole("button", { name: "Close menu" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
