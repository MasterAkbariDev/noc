import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { AppShell } from "./AppShell";

vi.mock("./StatusPill", () => ({ StatusPill: () => null }));
vi.mock("./UserMenu", () => ({ UserMenu: () => null }));
vi.mock("../components/ThemeToggle", () => ({ ThemeToggle: () => null }));

function renderShell() {
  render(
    <MemoryRouter initialEntries={["/incidents"]}>
      <AppShell>
        <p>Page body</p>
      </AppShell>
    </MemoryRouter>,
  );
}

function menuButton(): HTMLElement {
  return screen.getByRole("button", { name: "Menu" });
}

function isMenuOpen(): string | null {
  return menuButton().getAttribute("aria-expanded");
}

afterEach(() => {
  cleanup();
});

describe("AppShell phone menu", () => {
  it("opens and closes from the menu button", () => {
    renderShell();

    fireEvent.click(menuButton());
    expect(isMenuOpen()).toBe("true");

    fireEvent.click(menuButton());
    expect(isMenuOpen()).toBe("false");
  });

  it("closes on Escape and gives focus back to the menu button", () => {
    renderShell();
    fireEvent.click(menuButton());

    fireEvent.keyDown(document, { key: "Escape" });

    expect(isMenuOpen()).toBe("false");
    expect(document.activeElement).toBe(menuButton());
  });

  it("ignores other keys", () => {
    renderShell();
    fireEvent.click(menuButton());

    fireEvent.keyDown(document, { key: "Enter" });

    expect(isMenuOpen()).toBe("true");
  });

  it("closes on a pointer press outside the sidebar", () => {
    renderShell();
    fireEvent.click(menuButton());

    fireEvent.pointerDown(screen.getByText("Page body"));

    expect(isMenuOpen()).toBe("false");
  });

  it("stays open for a pointer press inside the sidebar", () => {
    renderShell();
    fireEvent.click(menuButton());

    fireEvent.pointerDown(screen.getByText("Multi-Agent NOC"));

    expect(isMenuOpen()).toBe("true");
  });

  it("does not reopen on the press that closes it from the menu button", () => {
    renderShell();
    fireEvent.click(menuButton());

    fireEvent.pointerDown(menuButton());
    fireEvent.click(menuButton());

    expect(isMenuOpen()).toBe("false");
  });
});
