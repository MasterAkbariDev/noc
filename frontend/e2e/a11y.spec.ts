import type { Locator, Page } from "@playwright/test";
import {
  ESCALATED_TITLE,
  USERS,
  expect,
  expectNoSeriousViolations,
  openEscalatedIncident,
  signIn,
  test,
} from "./support";

const THEMES = ["light", "dark"] as const;

type Scene = {
  name: string;
  open: (page: Page) => Promise<unknown>;
  ready: (page: Page) => Locator;
};

const AUTHENTICATED_SCENES: Scene[] = [
  {
    name: "overview",
    open: (page) => page.goto("/"),
    ready: (page) => page.getByRole("heading", { name: ESCALATED_TITLE }),
  },
  {
    name: "incidents",
    open: (page) => page.goto("/incidents"),
    ready: (page) => page.getByRole("link", { name: ESCALATED_TITLE }),
  },
  {
    name: "incident",
    open: openEscalatedIncident,
    ready: (page) => page.getByRole("heading", { level: 2, name: "What happened" }),
  },
  {
    name: "servers",
    open: (page) => page.goto("/servers"),
    ready: (page) => page.getByText("demo-1").first(),
  },
  {
    name: "system",
    open: (page) => page.goto("/system"),
    ready: (page) => page.getByRole("heading", { name: "Components" }),
  },
  {
    name: "activity",
    open: (page) => page.goto("/activity"),
    ready: (page) => page.getByRole("table"),
  },
  {
    name: "settings",
    open: (page) => page.goto("/settings"),
    ready: (page) => page.getByRole("heading", { name: "My account" }),
  },
];

for (const theme of THEMES) {
  test(`the login page has no serious accessibility violations in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/login");

    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expectNoSeriousViolations(page, `the login page in ${theme}`);
  });
}

for (const scene of AUTHENTICATED_SCENES) {
  for (const theme of THEMES) {
    test(`${scene.name} has no serious accessibility violations in ${theme}`, async ({ page }) => {
      await signIn(page, USERS.admin);
      await page.emulateMedia({ colorScheme: theme });
      await scene.open(page);

      await expect(scene.ready(page)).toBeVisible();
      await expectNoSeriousViolations(page, `${scene.name} in ${theme}`);
    });
  }
}
