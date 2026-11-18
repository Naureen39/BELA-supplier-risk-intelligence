import { expect, test } from "@playwright/test";
import { login, settle } from "./helpers";

test("marketing pages render with their headings, images, and no horizontal scroll", async ({
  page,
}) => {
  for (const [path, heading] of [
    ["/", /See every risk behind every supplier/],
    ["/pricing", /Plans sized by monitored suppliers/],
    ["/platform", /One pipeline/],
    ["/methodology", /How matching and scoring work/],
    ["/resources/measuring-a-matching-system", /Measuring a matching system/],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(heading);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});

test("security headers are served with the pages", async ({ request }) => {
  const r = await request.get("/");
  const h = r.headers();
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(h["content-security-policy"]).toContain("object-src 'none'");
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["x-content-type-options"]).toBe("nosniff");
  expect(h["strict-transport-security"]).toContain("max-age=");
  expect(h["referrer-policy"]).toBeTruthy();
  expect(h["permissions-policy"]).toContain("camera=()");
});

test("keyboard navigation: skip link, mega menu, and the mobile drawer", async ({
  page,
  browserName,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.keyboard.press("Tab");
  // Safari does not tab to links unless the OS setting is on, so the skip link is checked in the other engines.
  if (browserName !== "webkit")
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.locator("header").getByRole("button", { name: "Platform" }).click();
  await expect(
    page.locator("header").getByRole("link", { name: /Entity resolution/ }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 375, height: 800 });
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("the demo request form validates in the browser and the cookie notice works", async ({
  page,
}) => {
  await page.goto("/contact");
  await page.getByRole("button", { name: "Request a demo" }).click();
  await expect(page.getByText("Enter your name")).toBeVisible();
  await expect(page.getByText("Consent is required")).toBeVisible();
  await page.goto("/");
  const notice = page.getByRole("region", { name: "Cookie notice" });
  await notice.getByRole("button", { name: "Understood" }).click();
  await expect(notice).toBeHidden();
  await page.reload();
  await expect(notice).toBeHidden();
});

test("sign-in, then the application pages draw their charts and graph", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page, "manager@demo.example");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.goto("/app/analytics");
  await expect(page.getByRole("region", { name: "Key figures" }).locator("p.text-2xl")).toHaveCount(
    7,
    { timeout: 20_000 },
  );
  await settle(page);
  expect(await page.locator("canvas").count()).toBeGreaterThan(3); // ECharts draws on canvas
  await page.goto("/app/explorer?company=1");
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.goto("/app/reviews");
  await expect(page.getByRole("heading", { name: /Review queue|Record:/ }).first()).toBeVisible();
  await page.goto("/app/suppliers");
  await expect(page.getByRole("table", { name: "Suppliers" })).toBeVisible();
  // CSV export of the table downloads a file.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "CSV" }).click();
  expect((await download).suggestedFilename()).toBe("suppliers.csv");
});
