import { HOSTILE_TEXT, USERS, expect, openEscalatedIncident, signIn, test } from "./support";

const STORY_HEADINGS = ["What happened", "What we found", "What we did", "What you should do"];

test("the incident page shows the four story sections", async ({ page }) => {
  await signIn(page, USERS.admin);
  await openEscalatedIncident(page);

  for (const heading of STORY_HEADINGS) {
    await expect(page.getByRole("heading", { level: 2, name: heading })).toBeVisible();
  }
});

test("hostile text from the evidence is shown as text, not markup", async ({ page }) => {
  await signIn(page, USERS.admin);
  await openEscalatedIncident(page);

  await expect(page.locator("main script")).toHaveCount(0);
  await expect(page.getByText(HOSTILE_TEXT, { exact: false }).first()).toBeVisible();
});

test("the tabs switch and the choice is kept in the URL", async ({ page }) => {
  await signIn(page, USERS.admin);
  await openEscalatedIncident(page);

  await page.getByRole("tab", { name: "Agent activity" }).click();
  await expect(page).toHaveURL(/tab=activity/);
  await expect(page.getByRole("tab", { name: "Agent activity" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.getByRole("tab", { name: "Timeline" }).click();
  await expect(page).toHaveURL(/tab=timeline/);
});
