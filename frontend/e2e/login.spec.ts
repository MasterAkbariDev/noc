import { ESCALATED_TITLE, USERS, expect, openEscalatedIncident, signIn, test } from "./support";

test("a wrong password shows the plain message and no data", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill(USERS.admin);
  await page.getByLabel("Password").fill("not-the-password-at-all");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toHaveText("Invalid username or password.");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText(ESCALATED_TITLE)).toHaveCount(0);
});

test("the overview shows a verdict and the escalated incident", async ({ page }) => {
  await signIn(page, USERS.admin);

  await expect(page.getByLabel("Overall status")).toBeVisible();
  await expect(page.getByRole("heading", { name: ESCALATED_TITLE })).toBeVisible();
});

test("sign out returns to the login page and Back shows no data", async ({ page }) => {
  await signIn(page, USERS.admin);
  await openEscalatedIncident(page);
  await page.getByRole("button", { name: USERS.admin }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();

  await expect(page).toHaveURL(/\/login/);
  await page.goBack();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText(ESCALATED_TITLE)).toHaveCount(0);
});
