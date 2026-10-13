import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TargetView } from "../api/types";
import { formatTime } from "./format";
import { TargetCard } from "./TargetCard";

const NOW = new Date("2026-10-13T10:00:00Z");
const UNTRUSTED_NAME = '<img src=x onerror=alert(1)>edge-1';

function makeTarget(overrides: Partial<TargetView> = {}): TargetView {
  return {
    id: "33333333-3333-3333-3333-333333333333",
    name: "web-1",
    environment: "staging",
    automation_level: "auto",
    halted: false,
    last_inventory_at: "2026-10-13T09:58:00Z",
    resources: [{ resource_id: "svc-web", kind: "service", name: "nginx" }],
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("TargetCard", () => {
  it("shows the HALTED badge only when the target is halted", () => {
    const { unmount } = render(<TargetCard target={makeTarget()} />);
    expect(screen.queryByText("HALTED")).toBeNull();
    unmount();

    render(<TargetCard target={makeTarget({ halted: true })} />);
    expect(screen.getByText("HALTED")).toBeTruthy();
  });

  it("shows never when the target has no inventory time", () => {
    render(<TargetCard target={makeTarget({ last_inventory_at: null })} />);

    expect(screen.getByText("never")).toBeTruthy();
  });

  it("shows the inventory time relative to now, with the full time as a title", () => {
    render(<TargetCard target={makeTarget()} />);

    const time = screen.getByText("2 minutes ago");
    expect(time.tagName).toBe("TIME");
    expect(time.getAttribute("title")).toBe(formatTime("2026-10-13T09:58:00Z"));
  });

  it("highlights the prod environment badge only", () => {
    const { unmount } = render(<TargetCard target={makeTarget({ environment: "prod" })} />);
    expect(screen.getByText("prod").classList.contains("badge-prod")).toBe(true);
    unmount();

    render(<TargetCard target={makeTarget({ environment: "staging" })} />);
    expect(screen.getByText("staging").classList.contains("badge-prod")).toBe(false);
  });

  it("shows a hostile target name as text and creates no image element", () => {
    const { container } = render(<TargetCard target={makeTarget({ name: UNTRUSTED_NAME })} />);

    expect(screen.getByRole("heading", { name: UNTRUSTED_NAME })).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("lists the resources with their kind and name", () => {
    render(<TargetCard target={makeTarget()} />);

    expect(screen.getByText("service")).toBeTruthy();
    expect(screen.getByText("nginx")).toBeTruthy();
  });
});
