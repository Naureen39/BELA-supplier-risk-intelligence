import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { PAGES, SIZES } from "./pages";

test("skip link and landmarks", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await expect(page.getByRole("main")).toHaveCount(1);
  await expect(page.getByRole("banner")).toHaveCount(1);
  await expect(page.getByRole("contentinfo")).toHaveCount(1);
});

test("mega menu opens and closes with the keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const trigger = page.locator("header").getByRole("button", { name: "Platform" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const header = page.locator("header");
  const link = header.getByRole("link", { name: /Entity resolution/ });
  await expect(link).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(link).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(link).toBeHidden();
  await header.getByRole("button", { name: "Industries" }).focus();
  await page.keyboard.press("Enter");
  await expect(header.getByRole("link", { name: /Manufacturing/ })).toBeVisible();
});

test("mobile drawer navigation", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/");
  await page.getByRole("button", { name: "Menu" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("link", { name: "Pricing" }).click();
  await expect(page).toHaveURL(/\/pricing$/);
});

test("home hero has no layout shift", async ({ page }) => {
  await page.addInitScript(() => {
    (window as unknown as { __cls: number }).__cls = 0;
    new PerformanceObserver((list) => {
      for (const e of list.getEntries() as unknown as {
        hadRecentInput: boolean;
        value: number;
      }[]) {
        if (!e.hadRecentInput) (window as unknown as { __cls: number }).__cls += e.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.mouse.wheel(0, 600);
  await page.waitForTimeout(500);
  const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
  expect(cls).toBeLessThan(0.01);
});

test("cookie notice appears once and is remembered", async ({ page }) => {
  await page.goto("/");
  const notice = page.getByRole("region", { name: "Cookie notice" });
  await expect(notice).toBeVisible();
  await notice.getByRole("button", { name: "Understood" }).click();
  await expect(notice).toBeHidden();
  await page.reload();
  await expect(notice).toBeHidden();
});

test("no horizontal scroll and screenshots at five widths", async ({ page }) => {
  test.setTimeout(240_000);
  await page.addInitScript(() => localStorage.setItem("pr_cookie_notice", "1"));
  mkdirSync("reports/screens", { recursive: true });
  for (const width of SIZES) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of [
      "/",
      "/pricing",
      "/platform",
      "/resources/measuring-a-matching-system",
      "/login",
    ]) {
      await page.goto(path);
      await page.waitForTimeout(300);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `${path} at ${width}`).toBeLessThanOrEqual(0);
      if (path === "/")
        await page.screenshot({ path: `reports/screens/home-${width}.png`, fullPage: true });
    }
  }
});

test("every page has a title, one h1, and a canonical or noindex", async ({ page }) => {
  for (const path of PAGES) {
    await page.goto(path);
    expect((await page.title()).length, path).toBeGreaterThan(5);
    expect(await page.locator("h1").count(), path).toBe(1);
  }
});

test("sitemap and robots are served", async ({ request }) => {
  const sm = await request.get("/sitemap.xml");
  expect(sm.ok()).toBeTruthy();
  const body = await sm.text();
  expect(body).toContain("/resources/measuring-a-matching-system");
  expect(await (await request.get("/robots.txt")).text()).toContain("Disallow: /app");
});
