import AxeBuilder from "@axe-core/playwright";
import { expect, test as base, type Page } from "@playwright/test";
import { readEnv } from "./env";

export { expect };

export const USERS = {
  admin: "e2e-admin",
  operator: "e2e-operator",
  viewer: "e2e-viewer",
} as const;

export const ESCALATED_TITLE = "demo-shop.service is down after SIGKILL";
export const HOSTILE_TEXT = "<script>alert(1)</script>";

const MIN_PASSWORD_LENGTH = 12;
const CSP_MARKER = "Content Security Policy";

export function e2ePassword(): string {
  const password = readEnv("NOC_E2E_PASSWORD") ?? "";
  if (password.length < MIN_PASSWORD_LENGTH) {
    throw new Error(`NOC_E2E_PASSWORD must be set to at least ${MIN_PASSWORD_LENGTH} characters`);
  }
  return password;
}

export const test = base.extend<{ guard: void }>({
  guard: [
    async ({ page }, use) => {
      const cspMessages: string[] = [];
      const dialogs: string[] = [];
      page.on("console", (message) => {
        if (message.text().includes(CSP_MARKER)) {
          cspMessages.push(message.text());
        }
      });
      page.on("dialog", (dialog) => {
        dialogs.push(dialog.message());
        void dialog.dismiss();
      });
      await use();
      expect(cspMessages, "console messages about the Content Security Policy").toEqual([]);
      expect(dialogs, "JavaScript dialogs opened by the page").toEqual([]);
    },
    { auto: true },
  ],
});

export async function signIn(page: Page, username: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(e2ePassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
}

export async function openEscalatedIncident(page: Page): Promise<void> {
  await page.goto("/incidents");
  await page.getByRole("link", { name: ESCALATED_TITLE }).click();
  await expect(page.getByRole("heading", { level: 2, name: "What happened" })).toBeVisible();
}

export async function expectNoSeriousViolations(page: Page, scene: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const blocking = results.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      targets: violation.nodes.map((node) => node.target),
    }));
  expect(blocking, `serious or critical accessibility violations on ${scene}`).toEqual([]);
}
