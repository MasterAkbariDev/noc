import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { THEME_STORAGE_KEY, ThemeToggle } from "./ThemeToggle";

function themeAttribute(): string | null {
  return document.documentElement.getAttribute("data-theme");
}

function pressed(name: string): string | null {
  return screen.getByRole("button", { name }).getAttribute("aria-pressed");
}

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document.documentElement.removeAttribute("data-theme");
});

describe("ThemeToggle", () => {
  it("sets data-theme on the html element and remembers the choice", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(themeAttribute()).toBe("dark");
    expect(sessionStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(pressed("Dark")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Light" }));
    expect(themeAttribute()).toBe("light");
    expect(pressed("Light")).toBe("true");
    expect(pressed("Dark")).toBe("false");

    fireEvent.click(screen.getByRole("button", { name: "Auto" }));
    expect(themeAttribute()).toBeNull();
    expect(pressed("Auto")).toBe("true");
  });

  it("restores the stored choice on mount", () => {
    sessionStorage.setItem(THEME_STORAGE_KEY, "light");
    render(<ThemeToggle />);

    expect(themeAttribute()).toBe("light");
    expect(pressed("Light")).toBe("true");
  });

  it("ignores a stored value that is not a known theme", () => {
    sessionStorage.setItem(THEME_STORAGE_KEY, "<script>");
    render(<ThemeToggle />);

    expect(themeAttribute()).toBeNull();
    expect(pressed("Auto")).toBe("true");
  });

  it("still switches the theme when sessionStorage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(themeAttribute()).toBe("dark");
    expect(pressed("Dark")).toBe("true");
  });
});
