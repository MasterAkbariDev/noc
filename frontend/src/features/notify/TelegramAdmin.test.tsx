import {
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  getTelegram,
  removeTelegramToken,
  saveTelegram,
  setTelegramProxy,
  setTelegramToken,
  testTelegram,
} from "../../api/client";
import type { TelegramSettings } from "../../api/types";
import { useSession } from "../../auth/session";
import { sessionFor } from "../settings/fixtures";
import { renderWithProviders } from "../settings/harness";
import { TelegramAdmin } from "./TelegramAdmin";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getTelegram: vi.fn(),
  saveTelegram: vi.fn(),
  setTelegramToken: vi.fn(),
  removeTelegramToken: vi.fn(),
  setTelegramProxy: vi.fn(),
  testTelegram: vi.fn(),
}));

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

const EMPTY: TelegramSettings = {
  paused: false,
  panel_url: "",
  events: { opened: false, approval: true, escalated: true, resolved: true },
  admins: [],
  token_last4: null,
  proxy_display: null,
};

const READY: TelegramSettings = {
  ...EMPTY,
  token_last4: "x9Yz",
  admins: [
    { handle: "111111", username: "ali_ops", linked: true, muted: false },
    { handle: "@sara_ops", username: "sara_ops", linked: false, muted: false },
  ],
};

function renderAs(role: "operator" | "admin") {
  vi.mocked(useSession).mockReturnValue(
    sessionFor({ username: "admin", role, via: "session" }),
  );
  return renderWithProviders(<TelegramAdmin />);
}

beforeEach(() => {
  for (const mock of [
    getTelegram,
    saveTelegram,
    setTelegramToken,
    removeTelegramToken,
    setTelegramProxy,
    testTelegram,
  ]) {
    vi.mocked(mock).mockReset();
  }
  vi.mocked(useSession).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("TelegramAdmin", () => {
  it("is hidden from non-admins", () => {
    renderAs("operator");
    expect(screen.queryByRole("heading", { name: "Telegram" })).toBeNull();
  });

  it("saves a token, shows only its end and clears the field", async () => {
    vi.mocked(getTelegram).mockResolvedValue(EMPTY);
    vi.mocked(setTelegramToken).mockResolvedValue({
      ...EMPTY,
      token_last4: "abcd",
    });
    renderAs("admin");
    const field = await screen.findByLabelText("New bot token");
    expect(screen.getByText("not set")).toBeTruthy();
    fireEvent.change(field, { target: { value: " 123:secret " } });
    fireEvent.click(screen.getByRole("button", { name: "Save token" }));
    expect(await screen.findByText("…abcd")).toBeTruthy();
    expect(setTelegramToken).toHaveBeenCalledWith("123:secret");
    expect(
      (screen.getByLabelText("New bot token") as HTMLInputElement).value,
    ).toBe("");
  });

  it("lists admins with their bot status and saves added and removed ones", async () => {
    vi.mocked(getTelegram).mockResolvedValue(READY);
    vi.mocked(saveTelegram).mockResolvedValue(READY);
    renderAs("admin");
    const list = await screen.findByRole("list", { name: "Telegram admins" });
    expect(within(list).getByText("111111 (@ali_ops)")).toBeTruthy();
    expect(within(list).getByText("(gets messages)")).toBeTruthy();
    expect(
      within(list).getByText("(has not written to the bot yet)"),
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Telegram user id or @username"), {
      target: { value: " @new_admin " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove @sara_ops" }));
    fireEvent.change(screen.getByLabelText("Panel address for links"), {
      target: { value: "https://noc.example" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved the Telegram admins.")).toBeTruthy();
    expect(saveTelegram).toHaveBeenCalledWith({
      panel_url: "https://noc.example",
      admins: ["111111", "@new_admin"],
    });
  });

  it("shows what the bot sends and points to /settings", async () => {
    vi.mocked(getTelegram).mockResolvedValue({ ...READY, paused: true });
    renderAs("admin");
    expect(
      await screen.findByText(
        "Messages are paused. Sent when: approval needed or expired, escalated to a person, resolved.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("Change this in the bot with /settings."),
    ).toBeTruthy();
  });

  it("shows the server's reason when saving is refused", async () => {
    vi.mocked(getTelegram).mockResolvedValue(EMPTY);
    vi.mocked(saveTelegram).mockRejectedValue(
      new ApiError(
        422,
        "ali ops is not a Telegram user id (digits) or @username",
      ),
    );
    renderAs("admin");
    await screen.findByLabelText("Telegram user id or @username");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const card = screen.getByRole("region", { name: "Admins" });
    expect((await within(card).findByRole("alert")).textContent).toBe(
      "ali ops is not a Telegram user id (digits) or @username",
    );
  });

  it("sends a test message when a token and a linked admin are set", async () => {
    vi.mocked(getTelegram).mockResolvedValue(READY);
    vi.mocked(testTelegram).mockResolvedValue({
      ok: false,
      detail: "HTTP 400: chat not found",
    });
    renderAs("admin");
    const button = await screen.findByRole("button", {
      name: "Send test message",
    });
    fireEvent.click(button);
    expect(
      await screen.findByText("Test failed: HTTP 400: chat not found"),
    ).toBeTruthy();
  });

  it("disables the test until an admin has written to the bot", async () => {
    vi.mocked(getTelegram).mockResolvedValue({
      ...EMPTY,
      token_last4: "x9Yz",
      admins: [READY.admins[1]!],
    });
    renderAs("admin");
    const button = await screen.findByRole("button", {
      name: "Send test message",
    });
    expect(button.hasAttribute("disabled")).toBe(true);
  });

  it("saves an empty proxy as none", async () => {
    vi.mocked(getTelegram).mockResolvedValue({
      ...READY,
      proxy_display: "http://10.0.0.1:1",
    });
    vi.mocked(setTelegramProxy).mockResolvedValue(READY);
    renderAs("admin");
    await screen.findByLabelText(/Proxy URL/);
    fireEvent.click(screen.getByRole("button", { name: "Save proxy" }));
    await waitFor(() => expect(setTelegramProxy).toHaveBeenCalledWith(null));
  });
});
