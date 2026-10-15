import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { ServerResources } from "./ServerResources";
import { HOSTILE_IMG, serverSummary } from "./testData";

afterEach(() => {
  cleanup();
});

function renderResources(servers: Parameters<typeof ServerResources>[0]["servers"]) {
  return render(
    <MemoryRouter>
      <ServerResources servers={servers} />
    </MemoryRouter>,
  );
}

describe("ServerResources", () => {
  it("shows a row per server with its status, usage meters and a link", () => {
    renderResources([
      serverSummary({ name: "web-1", metrics: { cpu_percent: 91.4, memory_percent: 40, disk_percent: null, disk_mount: "/" } }),
    ]);

    const table = screen.getByRole("table", { name: "Server resources" });
    expect(within(table).getByRole("link", { name: "web-1" }).getAttribute("href")).toBe(
      "/servers/22222222-2222-2222-2222-222222222222",
    );
    expect(within(table).getByRole("meter", { name: "CPU on web-1" }).getAttribute("aria-valuetext")).toBe("91%");
    expect(within(table).getByText("No data")).toBeTruthy();
    expect(within(table).getByText("Up")).toBeTruthy();
  });

  it("says when there is no server and shows hostile names as text", () => {
    const { container, unmount } = renderResources([serverSummary({ name: HOSTILE_IMG })]);
    expect(screen.getByText(HOSTILE_IMG)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    unmount();

    renderResources([]);
    expect(screen.getByText("No servers yet.")).toBeTruthy();
  });
});
