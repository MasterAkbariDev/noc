import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CloseIncidentForm } from "./CloseIncidentForm";

const fetchMock = vi.fn<typeof fetch>();

function renderForm(status: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const view = render(
    <QueryClientProvider client={queryClient}>
      <CloseIncidentForm incidentId="abc" status={status} />
    </QueryClientProvider>,
  );
  return { ...view, invalidate };
}

function noteField(): HTMLTextAreaElement {
  return screen.getByLabelText(/Resolution note/) as HTMLTextAreaElement;
}

function checkbox(): HTMLInputElement {
  return screen.getByLabelText("I checked this incident") as HTMLInputElement;
}

function submitButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Close incident" }) as HTMLButtonElement;
}

beforeEach(() => {
  document.cookie = "noc_csrf=csrf-value; path=/";
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  document.cookie = "noc_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("CloseIncidentForm", () => {
  it("is hidden for every status except ESCALATED", () => {
    const { container } = renderForm("RESOLVED");

    expect(container.querySelector("form")).toBeNull();
    expect(screen.queryByText("Close this incident")).toBeNull();
  });

  it("keeps submit disabled until a note and the checkbox are both given", () => {
    renderForm("ESCALATED");

    expect(submitButton().disabled).toBe(true);

    fireEvent.change(noteField(), { target: { value: "   " } });
    fireEvent.click(checkbox());
    expect(submitButton().disabled).toBe(true);

    fireEvent.change(noteField(), { target: { value: "Restarted the service" } });
    expect(submitButton().disabled).toBe(false);

    fireEvent.click(checkbox());
    expect(submitButton().disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the note with the CSRF header and no bearer token, and refreshes the incident queries", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    const { invalidate } = renderForm("ESCALATED");

    fireEvent.change(noteField(), { target: { value: "  Restarted the service  " } });
    fireEvent.click(checkbox());
    fireEvent.click(submitButton());

    await waitFor(() => expect(invalidate).toHaveBeenCalledTimes(4));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["incidents"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["incident", "abc"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["story", "abc"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["overview"] });

    const url = fetchMock.mock.calls[0]?.[0];
    const init = fetchMock.mock.calls[0]?.[1];
    expect(url).toBe("/api/incidents/abc/close");
    expect(String(url)).not.toContain("csrf-value");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("csrf-value");
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
    expect(JSON.parse(String(init?.body))).toEqual({
      resolution_note: "Restarted the service",
      corrected_root_cause_code: null,
    });
  });

  it("shows the error text when the API answers 409", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 409, statusText: "Conflict" }));
    renderForm("ESCALATED");

    fireEvent.change(noteField(), { target: { value: "Restarted the service" } });
    fireEvent.click(checkbox());
    fireEvent.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toBe("409 Conflict");
  });
});
