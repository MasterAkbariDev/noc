import { USERS, expect, openEscalatedIncident, signIn, test } from "./support";

test("an operator closes the escalated incident", async ({ page }) => {
  await signIn(page, USERS.operator);
  await openEscalatedIncident(page);

  await page.getByRole("button", { name: "Close incident" }).click();
  const dialog = page.getByRole("dialog", { name: "Close this incident" });
  await dialog.getByLabel("Resolution note (required)").fill("Restarted demo-shop.service and checked its health.");
  await dialog.getByLabel("I checked this incident").check();
  await dialog.getByRole("button", { name: "Close incident" }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Close incident" })).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByText("Nothing needs you right now.")).toBeVisible();
});
