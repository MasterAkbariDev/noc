import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { refreshPeer, setPeerServerAutomation } from "../../api/client";
import type { PeerView } from "../../api/types";
import { useSession } from "../../auth/session";
import { sessionFor } from "../settings/fixtures";
import { summaryFixture } from "../servers/fixtures";
import { TooltipProvider } from "../../ui/Tooltip";
import { Toaster } from "../../ui/Toaster";
import { RemoteNodeGroup } from "./RemoteServers";

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  setPeerServerAutomation: vi.fn(),
  refreshPeer: vi.fn(),
}));

const PEER_ID = "11111111-1111-1111-1111-111111111111";

function peerFixture(): PeerView {
  return {
    id: PEER_ID,
    name: "stage-104",
    url: "https://104.example",
    direction: "follows",
    status: "paired",
    paired_at: "2026-10-17T10:00:00Z",
    expires_at: null,
    last_seen_at: "2026-10-18T10:00:00Z",
    last_error: null,
    last_status: {
      node_name: "stage-104",
      generated_at: "2026-10-18T10:00:00Z",
      servers: [summaryFixture({ name: "demo-1", automation_level: "auto_safe" })],
      endpoints: [],
      incidents: [],
    },
  } as PeerView;
}

function renderGroup(peer: PeerView) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Toaster>
        <TooltipProvider>
          <MemoryRouter>
            <RemoteNodeGroup peer={peer} />
          </MemoryRouter>
        </TooltipProvider>
      </Toaster>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(setPeerServerAutomation).mockReset();
  vi.mocked(refreshPeer).mockReset();
  vi.mocked(refreshPeer).mockResolvedValue(peerFixture());
});

afterEach(() => {
  cleanup();
});

describe("RemoteNodeGroup mode control", () => {
  it("lets an admin change a remote server's mode and reads the status back", async () => {
    vi.mocked(useSession).mockReturnValue(sessionFor({ username: "admin", role: "admin", via: "session" }));
    vi.mocked(setPeerServerAutomation).mockResolvedValue({ name: "demo-1", automation_level: "approval_required" });
    renderGroup(peerFixture());

    fireEvent.change(screen.getByLabelText("Mode of demo-1 on stage-104"), {
      target: { value: "approval_required" },
    });

    await waitFor(() =>
      expect(setPeerServerAutomation).toHaveBeenCalledWith(PEER_ID, "demo-1", "approval_required"),
    );
    await waitFor(() => expect(refreshPeer).toHaveBeenCalledWith(PEER_ID));
  });

  it("hides the mode control from viewers", () => {
    vi.mocked(useSession).mockReturnValue(sessionFor({ username: "viewer", role: "viewer", via: "session" }));
    renderGroup(peerFixture());

    expect(screen.queryByLabelText("Mode of demo-1 on stage-104")).toBeNull();
  });
});
