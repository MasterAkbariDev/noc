import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { KpiRow } from "./KpiRow";
import { overviewFixture } from "./testData";

function renderRow() {
  return render(
    <MemoryRouter>
      <KpiRow kpis={overviewFixture().kpis} />
    </MemoryRouter>,
  );
}

describe("KpiRow", () => {
  it("shows the four tiles as links to their pages", () => {
    renderRow();

    expect(screen.getByRole("link", { name: /Open incidents/ }).getAttribute("href")).toBe(
      "/incidents?filter=open",
    );
    expect(screen.getByRole("link", { name: /Needs you/ }).getAttribute("href")).toBe(
      "/incidents?filter=needs-you",
    );
    expect(screen.getByRole("link", { name: /Servers/ }).getAttribute("href")).toBe("/servers");
    expect(screen.getByRole("link", { name: /LLM keys/ }).getAttribute("href")).toBe("/system");
  });

  it("shows the counts as text", () => {
    renderRow();

    expect(screen.getByText("2/2")).toBeTruthy();
    expect(screen.getByText("9/10")).toBeTruthy();
  });

  it("shows Replay mode with the recorded answers hint in place of 0/0", () => {
    render(
      <MemoryRouter>
        <KpiRow kpis={{ ...overviewFixture().kpis, llm_keys_ok: 0, llm_keys_total: 0 }} llmMode="replay" />
      </MemoryRouter>,
    );

    expect(screen.getByText("Replay mode")).toBeTruthy();
    expect(screen.getByText("recorded answers")).toBeTruthy();
    expect(screen.queryByText("0/0")).toBeNull();
  });
});
