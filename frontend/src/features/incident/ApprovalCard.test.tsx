import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ActionView } from "../../api/types";
import { TooltipProvider } from "../../ui/Tooltip";
import { Toaster } from "../../ui/Toaster";
import { ApprovalCard } from "./ApprovalCard";

const HOSTILE_IMG = "<img src=x onerror=alert(1)>";
const HOSTILE_SCRIPT = "<script>alert(1)</script>";
const HASH = "a".repeat(64);
const INCIDENT_ID = "inc-1";
const ACTION_ID = "act-1";
const DECISION_PATH = `/api/incidents/${INCIDENT_ID}/actions/${ACTION_ID}/decision`;
const CHANGED_TEXT = "This request changed or expired — reload the incident.";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function minutesFromNow(minutes: number): string {
  return new Date(Date.now() + minutes * 60_000).toISOString();
}

function actionFixture(overrides: Partial<ActionView> = {}): ActionView {
  return {
    id: ACTION_ID,
    action_hash: HASH,
    rung: 1,
    authorization: null,
    approval_expires_at: minutesFromNow(30),
    dispatched_at: null,
    finished_at: null,
    result_code: null,
    action_type: "restart_service",
    resource_id: "web-1:nginx",
    status: "pending_approval",
    permission_class: "REQUIRES_APPROVAL",
    eligible: true,
    gate_failures: [],
    gate_text: [],
    reasons: [],
    impact_score: 3,
    high_impact: false,
    auto_executable: false,
    policy_version: "2026-10-skeleton-1",
    ...overrides,
  };
}

function cardTree(queryClient: QueryClient, action: ActionView, canDecide: boolean) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster>
          <ApprovalCard incidentId={INCIDENT_ID} action={action} canDecide={canDecide} />
        </Toaster>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

function renderCard(action: ActionView = actionFixture(), canDecide = true) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(cardTree(queryClient, action, canDecide));
  return { ...view, queryClient };
}

function sentBody(): unknown {
  return JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
}

function openDecision(name: "Approve" | "Reject") {
  fireEvent.click(screen.getByRole("button", { name }));
  return screen.getByRole("dialog", { name: `${name} this action` });
}

function buttonIsDisabled(name: string): boolean {
  return (screen.getByRole("button", { name }) as HTMLButtonElement).disabled;
}

beforeEach(() => {
  document.cookie = "noc_csrf=csrf-value; path=/";
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "clipboard");
  document.cookie = "noc_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("ApprovalCard", () => {
  it("shows the action, target, permission, impact and the hash it binds to", () => {
    const { container } = renderCard(actionFixture({ high_impact: true }));

    expect(screen.getByText("Waiting for your approval")).toBeTruthy();
    expect(screen.getByText("Restart service")).toBeTruthy();
    expect(screen.getByText("web-1:nginx")).toBeTruthy();
    expect(screen.getByText("Requires approval")).toBeTruthy();
    expect(screen.getByText("High impact")).toBeTruthy();
    expect(container.querySelector("code")?.textContent).toBe(HASH);
    expect(container.querySelector("time")?.getAttribute("title")).toBeTruthy();
  });

  it("hides Approve and Reject from a viewer and says who can decide", () => {
    renderCard(actionFixture(), false);

    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
    expect(screen.getByText("Only an operator or an admin can approve or reject this action.")).toBeTruthy();
    expect(screen.getByText("Waiting for an operator's decision.")).toBeTruthy();
  });

  it("tells an operator the incident is waiting for their decision", () => {
    renderCard();

    expect(screen.getByText("This incident is waiting for your decision.")).toBeTruthy();
  });

  it("shows the impact score and the hash inside the dialog it was captured for", () => {
    renderCard(actionFixture({ impact_score: 7 }));

    const dialog = openDecision("Approve");

    expect(within(dialog).getByText("Impact score: 7")).toBeTruthy();
    expect(within(dialog).getByText(HASH)).toBeTruthy();
  });

  it("sends the hash captured when the dialog opened, even if the action is refreshed meanwhile", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ approval_id: "ap-1", incident_status: "REMEDIATING" }));
    const view = renderCard();
    const dialog = openDecision("Approve");
    const refreshedHash = "b".repeat(64);

    view.rerender(cardTree(view.queryClient, actionFixture({ action_hash: refreshedHash }), true));
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve action" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(sentBody()).toEqual({ decision: "approved", action_hash: HASH, comment: null });
  });

  it("refetches the incident after a 409 so the page shows what changed", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "stale hash" }, 409));
    const { queryClient } = renderCard();
    const refetch = vi.spyOn(queryClient, "refetchQueries");

    fireEvent.click(within(openDecision("Approve")).getByRole("button", { name: "Approve action" }));

    expect(await screen.findByText(CHANGED_TEXT)).toBeTruthy();
    expect(refetch).toHaveBeenCalledWith({ queryKey: ["incident", INCIDENT_ID] });
  });

  it("shows the server's validation message, not the status line, for a 422", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ msg: "field required" }] }), {
        status: 422,
        statusText: "Unprocessable Content",
        headers: { "Content-Type": "application/json" },
      }),
    );
    renderCard();

    fireEvent.click(within(openDecision("Approve")).getByRole("button", { name: "Approve action" }));

    expect(await screen.findByText("field required")).toBeTruthy();
    expect(screen.queryByText(/422/)).toBeNull();
  });

  it("turns to expired by itself as the clock passes the expiry, without a reload", () => {
    vi.useFakeTimers();
    try {
      renderCard(actionFixture({ approval_expires_at: new Date(Date.now() + 90_000).toISOString() }));

      expect(screen.getByText("Expires in 1 min")).toBeTruthy();
      expect(buttonIsDisabled("Approve")).toBe(false);

      act(() => {
        vi.advanceTimersByTime(60_000);
      });
      expect(screen.getByText("Expires in under a minute")).toBeTruthy();

      act(() => {
        vi.advanceTimersByTime(30_000);
      });
      expect(screen.getByText("Expired")).toBeTruthy();
      expect(buttonIsDisabled("Approve")).toBe(true);
      expect(buttonIsDisabled("Reject")).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("opens the approve dialog with an optional comment limited to 500 characters", () => {
    renderCard();

    const dialog = openDecision("Approve");

    const comment = within(dialog).getByLabelText(/Comment/) as HTMLTextAreaElement;
    expect(comment.maxLength).toBe(500);
    expect(within(dialog).getByRole("button", { name: "Approve action" })).toBeTruthy();
  });

  it("sends the decision, the hash unchanged and the trimmed comment, and shows a success toast", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ approval_id: "ap-1", incident_status: "REMEDIATING" }));
    renderCard();

    const dialog = openDecision("Approve");
    fireEvent.change(within(dialog).getByLabelText(/Comment/), { target: { value: "  checked the logs  " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve action" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(DECISION_PATH);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(sentBody()).toEqual({ decision: "approved", action_hash: HASH, comment: "checked the logs" });
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-value");
    expect(await screen.findByText("Action approved.")).toBeTruthy();
  });

  it("sends a rejection with no comment when the comment is blank", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ approval_id: "ap-1", incident_status: "ESCALATED" }));
    renderCard();

    const dialog = openDecision("Reject");
    fireEvent.change(within(dialog).getByLabelText(/Comment/), { target: { value: "   " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reject action" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(sentBody()).toEqual({ decision: "rejected", action_hash: HASH, comment: null });
    expect(sentBody()).not.toHaveProperty("decided_by");
  });

  it("shows the reload message inline when the server answers 409 and keeps the dialog open", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "stale hash" }, 409));
    renderCard();

    const dialog = openDecision("Approve");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve action" }));

    expect(await within(dialog).findByRole("alert")).toBeTruthy();
    expect(screen.getByText(CHANGED_TEXT)).toBeTruthy();
    expect(screen.queryByText("stale hash")).toBeNull();
    expect(screen.getByRole("dialog", { name: "Approve this action" })).toBeTruthy();
  });

  it("asks for an authentication code on a production server and sends it with the approval", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "authentication code required" }, 403))
      .mockResolvedValueOnce(jsonResponse({ approval_id: "ap-1", incident_status: "REMEDIATING" }));
    renderCard();

    const dialog = openDecision("Approve");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve action" }));

    const field = await within(dialog).findByLabelText("Authentication code");
    expect(within(dialog).getByRole("alert").textContent).toBe(
      "This server is in production. Enter a code from your authenticator app to approve.",
    );
    fireEvent.change(field, { target: { value: " 123456 " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve action" }));

    expect(await screen.findByText("Action approved.")).toBeTruthy();
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      decision: "approved",
      action_hash: HASH,
      comment: null,
      totp: "123456",
    });
  });

  it("says when the code was refused and when two-factor is not set up", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "turn on two-factor authentication in Settings before approving production actions" }, 403),
    );
    renderCard();
    const dialog = openDecision("Approve");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve action" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain("turn on two-factor authentication");
    expect(within(dialog).queryByLabelText("Authentication code")).toBeNull();
  });

  it("disables both buttons and says so once the approval has expired", () => {
    renderCard(actionFixture({ approval_expires_at: new Date(Date.now() - 60_000).toISOString() }));

    expect(buttonIsDisabled("Approve")).toBe(true);
    expect(buttonIsDisabled("Reject")).toBe(true);
    expect(screen.getByText("Expired")).toBeTruthy();
    expect(screen.getByText("This request has expired. It can no longer be approved or rejected.")).toBeTruthy();
  });

  it("keeps the buttons enabled before the expiry", () => {
    renderCard();

    expect(buttonIsDisabled("Approve")).toBe(false);
    expect(buttonIsDisabled("Reject")).toBe(false);
  });

  it("copies the action hash and reports the copy", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(await screen.findByRole("button", { name: "Copied" })).toBeTruthy();
    expect(writeText).toHaveBeenCalledWith(HASH);
  });

  it("lists the gate checks that failed, or says none failed", () => {
    const { unmount } = renderCard(actionFixture({ gate_failures: ["protected_resource"] }));

    expect(screen.getByText("Failed:")).toBeTruthy();
    expect(screen.getByText("Protected resource")).toBeTruthy();
    unmount();

    renderCard(actionFixture());
    expect(screen.getByText("No gate check failed.")).toBeTruthy();
  });

  it("shows hostile action, target, reason and comment text as text and creates no element", () => {
    const { container } = renderCard(
      actionFixture({
        action_type: HOSTILE_IMG,
        resource_id: HOSTILE_SCRIPT,
        reasons: [HOSTILE_IMG],
        gate_failures: [HOSTILE_SCRIPT],
      }),
    );

    expect(screen.getAllByText(HOSTILE_IMG)).toHaveLength(2);
    expect(screen.getAllByText(HOSTILE_SCRIPT)).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();

    const dialog = openDecision("Reject");
    fireEvent.change(within(dialog).getByLabelText(/Comment/), { target: { value: HOSTILE_SCRIPT } });

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
});
