import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import type { AttentionItem } from "../../api/types";
import { Toaster } from "../../ui/Toaster";
import { NeedsAttention } from "./NeedsAttention";
import { HOSTILE_IMG, HOSTILE_SCRIPT, attentionItem } from "./testData";

function renderList(items: AttentionItem[], canClose: boolean) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Toaster>
        <MemoryRouter>
          <NeedsAttention items={items} canClose={canClose} />
        </MemoryRouter>
      </Toaster>
    </QueryClientProvider>,
  );
}

describe("NeedsAttention", () => {
  it("draws an empty list when nothing needs the operator, because the page hides the section", () => {
    renderList([], true);

    expect(screen.getByRole("list", { name: "Incidents that need you" }).children).toHaveLength(0);
  });

  it("shows the incident with its target and reason, and leaves the steps to the incident page", () => {
    renderList([attentionItem()], false);

    expect(screen.getByText("Disk almost full on demo-1")).toBeTruthy();
    expect(screen.getByText(/demo-1, waiting since/)).toBeTruthy();
    expect(screen.getByText("Logs are filling the root disk.")).toBeTruthy();
    expect(screen.queryByText("Review the logs and free space.")).toBeNull();
    expect(screen.getByRole("link", { name: "See the steps" }).getAttribute("href")).toBe(
      "/incidents/11111111-1111-1111-1111-111111111111",
    );
  });

  it("links an incident waiting for approval to its page as Review and approve", () => {
    renderList([attentionItem({ status: "AWAITING_APPROVAL", status_label: "Waiting for approval" })], true);

    expect(screen.getByRole("link", { name: "Review and approve" }).getAttribute("href")).toBe(
      "/incidents/11111111-1111-1111-1111-111111111111",
    );
    expect(screen.queryByRole("button", { name: "Mark resolved" })).toBeNull();
  });

  it("hides Mark resolved for a viewer", () => {
    renderList([attentionItem()], false);

    expect(screen.queryByRole("button", { name: "Mark resolved" })).toBeNull();
  });

  it("hides Mark resolved for an incident that is not escalated", () => {
    renderList([attentionItem({ status: "AWAITING_APPROVAL", status_label: "Waiting for approval" })], true);

    expect(screen.queryByRole("button", { name: "Mark resolved" })).toBeNull();
    expect(screen.getByText(/waiting for approval since/)).toBeTruthy();
  });

  it("opens the close form in a dialog for an operator on an escalated incident", () => {
    renderList([attentionItem()], true);

    fireEvent.click(screen.getByRole("button", { name: "Mark resolved" }));

    expect(screen.getByRole("dialog", { name: "Mark incident resolved" })).toBeTruthy();
    expect(screen.getByLabelText(/Resolution note/)).toBeTruthy();
  });

  it("drops the repeated title from the reason", () => {
    renderList([attentionItem({ title: "Disk full", summary: "Disk full needs you: no safe fix is allowed." })], false);

    expect(screen.getByText("No safe fix is allowed.")).toBeTruthy();
  });

  it("shows hostile title and summary as text and creates no element", () => {
    const { container } = renderList(
      [attentionItem({ title: HOSTILE_IMG, summary: HOSTILE_SCRIPT })],
      true,
    );

    expect(screen.getByText(HOSTILE_IMG)).toBeTruthy();
    expect(screen.getByText(`${HOSTILE_SCRIPT}.`)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});
