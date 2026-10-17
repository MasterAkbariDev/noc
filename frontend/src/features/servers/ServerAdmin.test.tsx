import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setServerAutomation } from "../../api/client";
import { useSession } from "../../auth/session";
import { sessionFor } from "../settings/fixtures";
import { renderWithProviders } from "../settings/harness";
import { summaryFixture } from "./fixtures";
import { ServerAdmin } from "./ServerAdmin";

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  setServerAutomation: vi.fn(),
  setServerLabel: vi.fn(),
}));

function renderAdmin() {
  return renderWithProviders(
    <ServerAdmin server={summaryFixture({ name: "demo-1", automation_level: "auto_safe" })} />,
  );
}

beforeEach(() => {
  vi.mocked(setServerAutomation).mockResolvedValue({ name: "demo-1", automation_level: "approval_required" });
});

afterEach(() => {
  cleanup();
  vi.mocked(setServerAutomation).mockReset();
});

describe("ServerAdmin", () => {
  it("shows the mode control to an admin and saves the chosen mode", async () => {
    vi.mocked(useSession).mockReturnValue(sessionFor({ username: "admin", role: "admin", via: "session" }));
    renderAdmin();
    fireEvent.change(screen.getByRole("combobox", { name: "Mode of demo-1" }), {
      target: { value: "approval_required" },
    });
    await waitFor(() => expect(setServerAutomation).toHaveBeenCalledWith("demo-1", "approval_required"));
  });

  it("hides the mode control from a viewer", () => {
    vi.mocked(useSession).mockReturnValue(sessionFor({ username: "viewer", role: "viewer", via: "session" }));
    renderAdmin();
    expect(screen.queryByRole("combobox", { name: "Mode of demo-1" })).toBeNull();
  });
});
