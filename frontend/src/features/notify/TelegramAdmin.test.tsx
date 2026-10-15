import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
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
  enabled: false,
  chat_id: "",
  panel_url: "",
  events: { opened: false, approval: true, escalated: true, resolved: true },
  token_last4: null,
  proxy_display: null,
};

const READY: TelegramSettings = { ...EMPTY, chat_id: "-100123", token_last4: "x9Yz" };

function renderAs(role: "operator" | "admin") {
  vi.mocked(useSession).mockReturnValue(sessionFor({ username: "admin", role, via: "session" }));
  return renderWithProviders(<TelegramAdmin />);
}

beforeEach(() => {
  for (const mock of [getTelegram, saveTelegram, setTelegramToken, removeTelegramToken, setTelegramProxy, testTelegram]) {
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
    vi.mocked(setTelegramToken).mockResolvedValue({ ...EMPTY, token_last4: "abcd" });
    renderAs("admin");
    const field = await screen.findByLabelText("New bot token");
    expect(screen.getByText("not set")).toBeTruthy();
    fireEvent.change(field, { target: { value: " 123:secret " } });
    fireEvent.click(screen.getByRole("button", { name: "Save token" }));
    expect(await screen.findByText("…abcd")).toBeTruthy();
    expect(setTelegramToken).toHaveBeenCalledWith("123:secret");
    expect((screen.getByLabelText("New bot token") as HTMLInputElement).value).toBe("");
  });

  it("saves chat, link address and event choices", async () => {
    vi.mocked(getTelegram).mockResolvedValue(READY);
    vi.mocked(saveTelegram).mockResolvedValue({ ...READY, enabled: true });
    renderAs("admin");
    await screen.findByLabelText("Chat id");
    fireEvent.click(screen.getByLabelText("Send notifications"));
    fireEvent.change(screen.getByLabelText("Panel address for links"), { target: { value: "https://noc.example" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Resolved/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /New incident/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Telegram notifications are on.")).toBeTruthy();
    expect(saveTelegram).toHaveBeenCalledWith({
      enabled: true,
      chat_id: "-100123",
      panel_url: "https://noc.example",
      events: { opened: true, approval: true, escalated: true, resolved: false },
    });
  });

  it("shows the server's reason when saving is refused", async () => {
    vi.mocked(getTelegram).mockResolvedValue(EMPTY);
    vi.mocked(saveTelegram).mockRejectedValue(new ApiError(422, "set a bot token and a chat id first"));
    renderAs("admin");
    await screen.findByLabelText("Chat id");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const card = screen.getByRole("region", { name: "Where and when" });
    expect((await within(card).findByRole("alert")).textContent).toBe("set a bot token and a chat id first");
  });

  it("sends a test message only when a token and chat are set", async () => {
    vi.mocked(getTelegram).mockResolvedValue(READY);
    vi.mocked(testTelegram).mockResolvedValue({ ok: false, detail: "HTTP 400: chat not found" });
    renderAs("admin");
    const button = await screen.findByRole("button", { name: "Send test message" });
    fireEvent.click(button);
    expect(await screen.findByText("Test failed: HTTP 400: chat not found")).toBeTruthy();
  });

  it("disables the test without a token", async () => {
    vi.mocked(getTelegram).mockResolvedValue(EMPTY);
    renderAs("admin");
    const button = await screen.findByRole("button", { name: "Send test message" });
    expect(button.hasAttribute("disabled")).toBe(true);
  });

  it("saves an empty proxy as none", async () => {
    vi.mocked(getTelegram).mockResolvedValue({ ...READY, proxy_display: "http://10.0.0.1:1" });
    vi.mocked(setTelegramProxy).mockResolvedValue(READY);
    renderAs("admin");
    await screen.findByLabelText(/Proxy URL/);
    fireEvent.click(screen.getByRole("button", { name: "Save proxy" }));
    await waitFor(() => expect(setTelegramProxy).toHaveBeenCalledWith(null));
  });
});
