import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TOKEN_STORAGE_KEY, TokenProvider } from "../auth/token";
import { CloseIncidentForm } from "./CloseIncidentForm";

const fetchMock = vi.fn<typeof fetch>();

function renderForm(status: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const view = render(
    <QueryClientProvider client={queryClient}>
      <TokenProvider>
        <CloseIncidentForm incidentId="abc" status={status} />
      </TokenProvider>
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
  sessionStorage.setItem(TOKEN_STORAGE_KEY, "secret-token");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  sessionStorage.clear();
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

  it("posts the note with the token in the header, not the URL, and refreshes the incident queries", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    const { invalidate } = renderForm("ESCALATED");

    fireEvent.change(noteField(), { target: { value: "  Restarted the service  " } });
    fireEvent.click(checkbox());
    fireEvent.click(submitButton());

    await waitFor(() => expect(invalidate).toHaveBeenCalledTimes(2));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["incidents"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["incident", "abc"] });

    const url = fetchMock.mock.calls[0]?.[0];
    const init = fetchMock.mock.calls[0]?.[1];
    expect(url).toBe("/api/incidents/abc/close");
    expect(String(url)).not.toContain("secret-token");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret-token");
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
