import type { Locator, Page } from "@playwright/test";
import { USERS, expect, signIn, test } from "./support";

const WAITING_TITLE = "demo-shop.service start needs your approval";
const EXPIRED_TITLE = "demo-web.service start approval expired";
const HASH_PATTERN = /^[0-9a-f]{64}$/;

function attentionRow(page: Page, title: string): Locator {
  return page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: title }) });
}

async function openFromIncidents(page: Page, title: string): Promise<void> {
  await page.goto("/incidents");
  await page.getByRole("link", { name: title }).click();
  await expect(page.getByRole("heading", { level: 2, name: "What happened" })).toBeVisible();
}

test("a viewer sees the approval card of a waiting incident without any decision buttons", async ({
  page,
}) => {
  await signIn(page, USERS.viewer);
  await openFromIncidents(page, WAITING_TITLE);

  await expect(page.getByRole("heading", { level: 2, name: "Waiting for your approval" })).toBeVisible();
  await expect(page.getByText("Waiting for an operator's decision.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
});

test("an expired approval shows Expired and its buttons are disabled", async ({ page }) => {
  await signIn(page, USERS.operator);
  await openFromIncidents(page, EXPIRED_TITLE);

  await expect(page.getByRole("heading", { level: 2, name: "Waiting for your approval" })).toBeVisible();
  await expect(page.getByText("Expired", { exact: true })).toBeVisible();
  await expect(page.getByText("This request has expired.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reject" })).toBeDisabled();
});

test("the operator reaches the waiting incident from the overview and sees the card above the story", async ({
  page,
}) => {
  await signIn(page, USERS.operator);
  await attentionRow(page, WAITING_TITLE).getByRole("link", { name: "Review and approve" }).click();

  const card = page.getByRole("heading", { level: 2, name: "Waiting for your approval" });
  const story = page.getByRole("heading", { level: 2, name: "What happened" });
  await expect(card).toBeVisible();
  await expect(story).toBeVisible();
  const cardBox = await card.boundingBox();
  const storyBox = await story.boundingBox();
  expect(cardBox).not.toBeNull();
  expect(storyBox).not.toBeNull();
  expect(cardBox?.y ?? Infinity).toBeLessThan(storyBox?.y ?? 0);
});

test("approving shows the action hash in the dialog and changes the story", async ({ page }) => {
  await signIn(page, USERS.operator);
  await attentionRow(page, WAITING_TITLE).getByRole("link", { name: "Review and approve" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Waiting for your approval" })).toBeVisible();
  const cardHash = (await page.locator("code").filter({ hasText: HASH_PATTERN }).first().textContent()) ?? "";
  expect(cardHash).toMatch(HASH_PATTERN);

  await page.getByRole("button", { name: "Approve", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Approve this action" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("code")).toHaveText(cardHash);

  await dialog.getByRole("button", { name: "Approve action" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("heading", { level: 2, name: "Waiting for your approval" })).toHaveCount(0);
  await expect(page.getByText("Waiting for approval")).toHaveCount(0);
});
