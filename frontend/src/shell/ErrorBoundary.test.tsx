import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

function Broken(): never {
  throw new Error("render failed");
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ErrorBoundary", () => {
  it("renders its children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>Healthy page</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("Healthy page")).toBeTruthy();
  });

  it("shows a recovery state instead of a child that throws", () => {
    render(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert").textContent).toContain("Something went wrong");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
