import type { Page } from "@playwright/test";
import { ESCALATED_TITLE, USERS, expect, openEscalatedIncident, signIn, test } from "./support";

const PHONE_WIDTH = 375;
const PHONE_HEIGHT = 812;

test.use({ viewport: { width: PHONE_WIDTH, height: PHONE_HEIGHT } });

const PHONE_SCENES: { name: string; open: (page: Page) => Promise<unknown>; ready: (page: Page) => Promise<unknown> }[] = [
  {
    name: "overview",
    open: (page) => page.goto("/"),
    ready: (page) => expect(page.getByLabel("Overall status")).toBeVisible(),
  },
  {
    name: "incidents",
    open: (page) => page.goto("/incidents"),
    ready: (page) => expect(page.getByRole("link", { name: ESCALATED_TITLE })).toBeVisible(),
  },
  {
    name: "incident",
    open: openEscalatedIncident,
    ready: (page) => expect(page.getByRole("heading", { level: 2, name: "What happened" })).toBeVisible(),
  },
  {
    name: "servers",
    open: (page) => page.goto("/servers"),
    ready: (page) => expect(page.getByText("demo-1").first()).toBeVisible(),
  },
  {
    name: "system",
    open: (page) => page.goto("/system"),
    ready: (page) => expect(page.getByRole("heading", { name: "Components" })).toBeVisible(),
  },
  {
    name: "activity",
    open: (page) => page.goto("/activity"),
    ready: (page) => expect(page.getByRole("table")).toBeVisible(),
  },
  {
    name: "settings",
    open: (page) => page.goto("/settings"),
    ready: (page) => expect(page.getByRole("heading", { name: "My account" })).toBeVisible(),
  },
];

for (const scene of PHONE_SCENES) {
  test(`${scene.name} does not scroll sideways at phone width`, async ({ page }) => {
    await signIn(page, USERS.admin);
    await scene.open(page);
    await scene.ready(page);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth, `page width on ${scene.name}`).toBeLessThanOrEqual(PHONE_WIDTH);
  });
}

test("the menu button opens the sidebar and Escape closes it with focus back on the button", async ({
  page,
}) => {
  await signIn(page, USERS.admin);
  const sidebar = page.locator("#app-sidebar");
  const menuButton = page.getByRole("button", { name: "Menu", exact: true });

  await expect(sidebar).toBeHidden();
  await menuButton.click();
  await expect(sidebar).toBeVisible();
  await expect(menuButton).toHaveAttribute("aria-expanded", "true");

  await page.keyboard.press("Escape");
  await expect(sidebar).toBeHidden();
  await expect(menuButton).toBeFocused();
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");
});
