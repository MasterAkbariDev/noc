import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import type { ServerSummary } from "../../api/types";
import { ServerList } from "./ServerList";
import { HOSTILE_IMG, serverSummary } from "./testData";

function renderList(servers: ServerSummary[]) {
  return render(
    <MemoryRouter>
      <ServerList servers={servers} />
    </MemoryRouter>,
  );
}

describe("ServerList", () => {
  it("shows the empty text when there are no servers", () => {
    renderList([]);

    expect(screen.getByText("No servers yet.")).toBeTruthy();
  });

  it("shows the status label, the name as a link, the environment and the headline", () => {
    renderList([serverSummary({ status: "down", environment: "prod", headline: "Not answering" })]);

    expect(screen.getByText("Down")).toBeTruthy();
    expect(screen.getByRole("link", { name: "demo-1" }).getAttribute("href")).toBe(
      "/servers/22222222-2222-2222-2222-222222222222",
    );
    expect(screen.getByText("prod")).toBeTruthy();
    expect(screen.getByText("Not answering")).toBeTruthy();
  });

  it("shows a hostile server name as text and creates no element", () => {
    const { container } = renderList([serverSummary({ name: HOSTILE_IMG })]);

    expect(screen.getByText(HOSTILE_IMG)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
