import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  addLlmKey,
  checkAllLlmProxies,
  checkLlmKey,
  checkLlmProxy,
  getLlmConfig,
  resetLlmChain,
  revokeLlmKey,
  setLlmChain,
  setLlmProxy,
} from "../../api/client";
import type { LlmChainOption, LlmConfig, LlmManagedKey } from "../../api/types";
import { useSession } from "../../auth/session";
import { sessionFor } from "../settings/fixtures";
import { renderWithProviders } from "../settings/harness";
import { LlmAdmin } from "./LlmAdmin";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getLlmConfig: vi.fn(),
  addLlmKey: vi.fn(),
  revokeLlmKey: vi.fn(),
  checkLlmKey: vi.fn(),
  setLlmProxy: vi.fn(),
  resetLlmProxy: vi.fn(),
  checkLlmProxy: vi.fn(),
  checkAllLlmProxies: vi.fn(),
  setLlmChain: vi.fn(),
  resetLlmChain: vi.fn(),
}));

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

const PANEL_KEY: LlmManagedKey = {
  id: "k-1",
  label: "gemini#aaaa1111",
  provider: "gemini",
  name: "main gemini",
  tier: "paid",
  source: "panel",
  last4: "9xYz",
  created_at: "2026-10-14T10:00:00Z",
  created_by: "admin",
};

const ENV_KEY: LlmManagedKey = {
  id: null,
  label: "groq#bbbb2222",
  provider: "groq",
  name: null,
  tier: "free",
  source: "env",
  last4: "abcd",
  created_at: null,
  created_by: null,
};

const CHAIN_OPTIONS: LlmChainOption[] = [
  { entry: "gemini:small", provider: "gemini", model_tier: "small", model: "gemini-3.1-flash-lite" },
  { entry: "gemini:strong", provider: "gemini", model_tier: "strong", model: "gemini-3.6-flash" },
  { entry: "groq:small", provider: "groq", model_tier: "small", model: "openai/gpt-oss-120b" },
  { entry: "groq:strong", provider: "groq", model_tier: "strong", model: "openai/gpt-oss-120b" },
];

function config(changes: Partial<LlmConfig> = {}): LlmConfig {
  return {
    mode: "live",
    secrets_persistent: true,
    providers: [
      {
        name: "gemini",
        base_url: "https://generativelanguage.googleapis.com/v1beta/openai/",
        proxy: { display: "http://***@10.0.0.9:3128", source: "panel" },
        free_models: [{ tier: "small", model: "gemini-3.1-flash-lite", rpm: 12, rpd: 800 }],
        paid_models: [
          {
            tier: "small",
            model: "gemini-3.1-flash-lite",
            rpm: 300,
            rpd: 20000,
          },
        ],
      },
      {
        name: "groq",
        base_url: "https://api.groq.com/openai/v1",
        proxy: { display: null, source: "none" },
        free_models: [{ tier: "small", model: "openai/gpt-oss-120b", rpm: 25, rpd: 900 }],
        paid_models: [],
      },
    ],
    keys: [PANEL_KEY, ENV_KEY],
    chains: [
      {
        tier: "small",
        customized: false,
        entries: [
          { ...CHAIN_OPTIONS[2]!, degraded: false },
          { ...CHAIN_OPTIONS[0]!, degraded: false },
          { ...CHAIN_OPTIONS[1]!, degraded: true },
        ],
      },
      {
        tier: "strong",
        customized: false,
        entries: [
          { ...CHAIN_OPTIONS[3]!, degraded: false },
          { ...CHAIN_OPTIONS[1]!, degraded: false },
        ],
      },
    ],
    chain_options: CHAIN_OPTIONS,
    ...changes,
  };
}

function nth(elements: HTMLElement[], index: number): HTMLElement {
  const element = elements[index];
  if (element === undefined) {
    throw new Error(`no element at ${index}`);
  }
  return element;
}

function renderAs(role: "viewer" | "operator" | "admin") {
  vi.mocked(useSession).mockReturnValue(sessionFor({ username: "admin", role, via: "session" }));
  return renderWithProviders(<LlmAdmin />);
}

beforeEach(() => {
  for (const mock of [
    getLlmConfig,
    addLlmKey,
    revokeLlmKey,
    checkLlmKey,
    setLlmProxy,
    checkLlmProxy,
    checkAllLlmProxies,
    setLlmChain,
    resetLlmChain,
  ]) {
    vi.mocked(mock).mockReset();
  }
  vi.mocked(useSession).mockReset();
  vi.mocked(getLlmConfig).mockResolvedValue(config());
});

afterEach(() => {
  cleanup();
});

describe("LlmAdmin", () => {
  it("is hidden from anyone who is not an admin", () => {
    renderAs("operator");
    expect(screen.queryByRole("heading", { name: "Language models" })).toBeNull();
    expect(getLlmConfig).not.toHaveBeenCalled();
  });

  it("lists providers with their proxy and limits, and keys with tier and source", async () => {
    renderAs("admin");
    const table = await screen.findByRole("table", { name: "API keys" });
    expect(within(table).getByText("main gemini")).toBeTruthy();
    expect(within(table).getByText("Paid tier")).toBeTruthy();
    expect(within(table).getByText("Environment (read-only)")).toBeTruthy();
    expect(within(table).getByText("gemini · …9xYz")).toBeTruthy();
    expect(screen.getByText("http://***@10.0.0.9:3128")).toBeTruthy();
    const limits = screen.getByRole("table", { name: "Limits for gemini" });
    expect(within(limits).getByText("300/min, 20000/day")).toBeTruthy();
    expect(within(screen.getByRole("table", { name: "Limits for groq" })).getByText("same as free")).toBeTruthy();
  });

  it("offers revoke only for keys added in the panel", async () => {
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    expect(screen.getByRole("button", { name: "Revoke main gemini" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Revoke groq key" })).toBeNull();
  });

  it("warns when the secrets folder is not on a volume", async () => {
    vi.mocked(getLlmConfig).mockResolvedValue(config({ secrets_persistent: false }));
    renderAs("admin");
    expect(await screen.findByText(/not on a mounted volume/)).toBeTruthy();
  });

  it("adds a key with provider, tier, name and secret, then clears the secret", async () => {
    vi.mocked(addLlmKey).mockResolvedValue({
      ...PANEL_KEY,
      id: "k-2",
      name: "groq paid",
      last4: "7777",
    });
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    fireEvent.click(screen.getByRole("button", { name: "Add API key" }));

    const dialog = screen.getByRole("dialog", { name: "Add an API key" });
    fireEvent.change(within(dialog).getByLabelText("Provider"), {
      target: { value: "groq" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Billing tier/), {
      target: { value: "paid" },
    });
    fireEvent.change(within(dialog).getByLabelText("Name"), {
      target: { value: " groq paid " },
    });
    fireEvent.change(within(dialog).getByLabelText("API key"), {
      target: { value: " gsk_secret_value " },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add key" }));

    expect(await screen.findByText("Added groq paid (…7777). Agents use it within a minute.")).toBeTruthy();
    expect(addLlmKey).toHaveBeenCalledWith({
      provider: "groq",
      tier: "paid",
      name: "groq paid",
      secret: "gsk_secret_value",
    });
  });

  it("shows the server's reason when a key is refused", async () => {
    vi.mocked(addLlmKey).mockRejectedValue(new ApiError(422, "this key is already configured"));
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    fireEvent.click(screen.getByRole("button", { name: "Add API key" }));
    const dialog = screen.getByRole("dialog", { name: "Add an API key" });
    fireEvent.change(within(dialog).getByLabelText("Name"), {
      target: { value: "x" },
    });
    fireEvent.change(within(dialog).getByLabelText("API key"), {
      target: { value: "abcdefgh123" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add key" }));
    expect((await within(dialog).findByRole("alert")).textContent).toBe("this key is already configured");
  });

  it("checks a key and shows the result next to it", async () => {
    vi.mocked(checkLlmKey).mockResolvedValue({
      ok: true,
      latency_ms: 1200,
      model: "gemini-3.1-flash-lite",
      detail: "answered: OK",
    });
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    fireEvent.click(screen.getByRole("button", { name: "Check main gemini" }));
    expect(await screen.findByText("Works in 1.2 s (gemini-3.1-flash-lite): answered: OK")).toBeTruthy();
    expect(checkLlmKey).toHaveBeenCalledWith("gemini#aaaa1111");
  });

  it("revokes after confirmation", async () => {
    vi.mocked(revokeLlmKey).mockResolvedValue(undefined);
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    fireEvent.click(screen.getByRole("button", { name: "Revoke main gemini" }));
    const dialog = screen.getByRole("dialog", { name: "Revoke main gemini?" });
    expect(revokeLlmKey).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke key" }));
    expect(await screen.findByText("Revoked main gemini. Its file was deleted.")).toBeTruthy();
    expect(revokeLlmKey).toHaveBeenCalledWith("k-1");
  });

  it("saves a proxy and checks it", async () => {
    vi.mocked(setLlmProxy).mockResolvedValue(config());
    vi.mocked(checkLlmProxy).mockResolvedValue({
      ok: false,
      latency_ms: 0,
      model: null,
      detail: "ConnectError: refused",
    });
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    fireEvent.click(nth(screen.getAllByRole("button", { name: "Change proxy" }), 1));
    const dialog = screen.getByRole("dialog", { name: "Proxy for groq" });
    fireEvent.change(within(dialog).getByLabelText("New proxy URL"), {
      target: { value: "http://10.0.0.1:3128" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save proxy" }));
    await waitFor(() => expect(setLlmProxy).toHaveBeenCalledWith("groq", "http://10.0.0.1:3128"));

    fireEvent.click(nth(screen.getAllByRole("button", { name: "Check proxy" }), 0));
    expect(await screen.findByText("Failed: ConnectError: refused")).toBeTruthy();
  });

  it("checks every proxy with one button and shows each result on its provider", async () => {
    vi.mocked(checkAllLlmProxies).mockResolvedValue([
      { provider: "gemini", ok: true, latency_ms: 120, model: null, detail: "reached the provider, HTTP 404" },
    ]);
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    fireEvent.click(screen.getByRole("button", { name: "Check all proxies" }));
    expect(await screen.findByText("Works in 0.1 s: reached the provider, HTTP 404")).toBeTruthy();
    expect(checkAllLlmProxies).toHaveBeenCalledTimes(1);
  });

  it("says which proxies failed when a check-all finds a broken one", async () => {
    vi.mocked(checkAllLlmProxies).mockResolvedValue([
      { provider: "gemini", ok: false, latency_ms: 10000, model: null, detail: "ConnectTimeout" },
    ]);
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    fireEvent.click(screen.getByRole("button", { name: "Check all proxies" }));
    expect(await screen.findByText("1 of 1 proxies failed: gemini.")).toBeTruthy();
  });

  it("moves a model up in the order and saves it", async () => {
    vi.mocked(setLlmChain).mockResolvedValue(config());
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    fireEvent.click(screen.getByRole("button", { name: "Move gemini · gemini-3.1-flash-lite up in the small order" }));
    fireEvent.click(nth(screen.getAllByRole("button", { name: "Save order" }), 0));
    await waitFor(() =>
      expect(setLlmChain).toHaveBeenCalledWith("small", ["gemini:small", "groq:small", "gemini:strong"]),
    );
  });

  it("does not offer to save an order nobody changed", async () => {
    renderAs("admin");
    await screen.findByRole("table", { name: "API keys" });
    expect((nth(screen.getAllByRole("button", { name: "Save order" }), 0) as HTMLButtonElement).disabled).toBe(true);
    expect(setLlmChain).not.toHaveBeenCalled();
  });
});
