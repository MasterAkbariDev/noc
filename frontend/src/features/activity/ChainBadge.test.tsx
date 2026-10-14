import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, verifyActivity } from "../../api/client";
import { ChainBadge } from "./ChainBadge";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  verifyActivity: vi.fn(),
}));

function renderBadge() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ChainBadge />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(verifyActivity).mockReset();
});

describe("ChainBadge", () => {
  it("says the audit log is intact when the chain verifies", async () => {
    vi.mocked(verifyActivity).mockResolvedValue({ ok: true, broken_at: null });
    renderBadge();

    expect(await screen.findByText("Audit log intact")).toBeTruthy();
  });

  it("names the broken entry when the chain does not verify", async () => {
    vi.mocked(verifyActivity).mockResolvedValue({ ok: false, broken_at: 9 });
    renderBadge();

    expect(await screen.findByText("Audit log broken at entry 9")).toBeTruthy();
  });

  it("shows a checking label while the first answer is pending", () => {
    vi.mocked(verifyActivity).mockReturnValue(new Promise(() => undefined));
    renderBadge();

    expect(screen.getByText("Checking the audit log…")).toBeTruthy();
  });

  it("offers to check again when the check fails", async () => {
    vi.mocked(verifyActivity).mockRejectedValueOnce(new ApiError(500, "database is busy"));
    vi.mocked(verifyActivity).mockResolvedValueOnce({ ok: true, broken_at: null });
    renderBadge();

    expect(await screen.findByText("Audit log not checked")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));

    expect(await screen.findByText("Audit log intact")).toBeTruthy();
  });
});
