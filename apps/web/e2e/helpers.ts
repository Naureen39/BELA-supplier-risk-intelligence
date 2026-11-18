import { expect, type Page } from "@playwright/test";

export const PASSWORD = "Violet-Harbor-Quartz-7421";

export async function login(page: Page, email: string): Promise<void> {
  await page.addInitScript(() => localStorage.setItem("pr_cookie_notice", "1"));
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app/);
  await expect(page.getByRole("navigation", { name: "Application" })).toBeVisible();
}

/** Wait for loading skeletons to go. The live alert stream keeps a connection open, so networkidle never settles. */
export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("load");
  await expect(page.locator("[aria-busy=true]")).toHaveCount(0, { timeout: 20_000 });
  await page.waitForTimeout(600);
}
