import { USERS, expect, openEscalatedIncident, signIn, test } from "./support";

test("a viewer reads the incident but cannot close it", async ({ page }) => {
  await signIn(page, USERS.viewer);
  await openEscalatedIncident(page);

  await expect(page.getByRole("button", { name: "Close incident" })).toHaveCount(0);
});

test("a viewer does not see the resolve action on the overview", async ({ page }) => {
  await signIn(page, USERS.viewer);

  await expect(page.getByRole("button", { name: "Mark resolved" })).toHaveCount(0);
});

test("a viewer does not see the users section in settings", async ({ page }) => {
  await signIn(page, USERS.viewer);
  await page.goto("/settings");

  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Users" })).toHaveCount(0);
});
