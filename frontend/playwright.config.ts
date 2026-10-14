import { defineConfig, devices } from "@playwright/test";
import { readEnv } from "./e2e/env";

const isCi = Boolean(readEnv("CI"));

export default defineConfig({
  testDir: "./e2e",
  outputDir: "dist/test-results",
  forbidOnly: isCi,
  fullyParallel: false,
  retries: isCi ? 1 : 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "dist/playwright-report", open: "never" }],
  ],
  use: {
    baseURL: readEnv("E2E_BASE_URL") ?? "http://localhost:8000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
