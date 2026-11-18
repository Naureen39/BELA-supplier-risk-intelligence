import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { login, settle } from "./helpers";
import { totp } from "./totp";

const axeResults: Record<string, unknown> = {};
const MANAGER_PAGES: [string, string][] = [
  ["/app", "Overview"],
  ["/app/suppliers", "Suppliers"],
  ["/app/reviews", "Review queue"],
  ["/app/events", "Events"],
  ["/app/events/1", "OSHA inspection record: Northgate Metals of Texas LLC"],
  ["/app/alerts", "Alerts"],
  ["/app/explorer?company=1", "Corporate explorer"],
  ["/app/sources", "Data sources"],
  ["/app/reports", "Reports"],
  ["/app/analytics", "Analytics"],
  ["/app/settings", "Settings"],
];

async function axe(page: import("@playwright/test").Page, name: string) {
  const r = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .analyze();
  axeResults[name] = {
    violations: r.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.map((n) => n.target.join(" ")),
    })),
    passes: r.passes.length,
  };
  expect(
    r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`),
    name,
  ).toEqual([]);
}

test.afterAll(() => {
  mkdirSync("reports", { recursive: true });
  writeFileSync("reports/axe-app.json", JSON.stringify(axeResults, null, 2));
});

test("manager: every page loads against the live API and passes axe in both themes", async ({
  page,
}) => {
  test.setTimeout(300_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page, "manager@demo.example");
  for (const [path, heading] of MANAGER_PAGES) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, exact: false }).first()).toBeVisible();
    await settle(page);
    await expect(page.getByRole("alert").filter({ hasText: "could not be loaded" })).toHaveCount(0);
    await axe(page, `light ${path}`);
  }
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  for (const [path] of MANAGER_PAGES) {
    await page.goto(path);
    await settle(page);
    await axe(page, `dark ${path}`);
  }
  expect(errors).toEqual([]);
});

test("manager: charts offer a table view and CSV", async ({ page }) => {
  await login(page, "manager@demo.example");
  await page.goto("/app/analytics");
  await expect(page.getByRole("region", { name: "Key figures" }).locator("p.text-2xl")).toHaveCount(
    7,
    { timeout: 20_000 },
  );
  await settle(page);
  const card = page
    .getByRole("heading", { name: "Suppliers by risk level" })
    .locator("xpath=ancestor::div[contains(@class,'p-5')][1]");
  await card.getByRole("button", { name: "Table" }).click();
  await expect(
    page.getByRole("region", { name: "Suppliers by risk level, data table" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "30 days", exact: true }).click();
  await page.getByLabel("Compare with the previous period").check();
  await settle(page);
  await expect(page.getByText("versus the previous period").first()).toBeAttached();
});

test("viewer: navigation hides restricted pages and the API still refuses them", async ({
  page,
}) => {
  await login(page, "viewer@demo.example");
  const nav = page.getByRole("navigation", { name: "Application" });
  for (const hidden of [
    "Review queue",
    "Analytics",
    "Reports",
    "Data sources",
    "Billing",
    "Administration",
    "Revenue",
  ]) {
    await expect(nav.getByRole("link", { name: hidden })).toHaveCount(0);
  }
  for (const visible of ["Overview", "Suppliers", "Alerts", "Events", "Explorer", "Settings"])
    await expect(nav.getByRole("link", { name: visible })).toBeVisible();
  await page.goto("/app/analytics");
  await expect(page.getByRole("alert").first()).toContainText(/permission|could not be loaded/i);
  await page.goto("/app/suppliers");
  await expect(page.getByRole("button", { name: "Upload suppliers" })).toHaveCount(0);
});

test("finance analyst sees only revenue and settings", async ({ page }) => {
  await login(page, "finance@demo.example");
  const nav = page.getByRole("navigation", { name: "Application" });
  await expect(nav.getByRole("link", { name: "Revenue" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Suppliers" })).toHaveCount(0);
  await nav.getByRole("link", { name: "Revenue" }).click();
  await expect(page.getByRole("heading", { name: "Revenue" }).first()).toBeVisible();
});

test("finance: revenue dashboard shows ten KPIs, an estimate label, and a customer drill-down", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await login(page, "finance@demo.example");
  await page.goto("/app/platform/revenue");
  await expect(page.getByRole("region", { name: "Key figures" }).locator("p.text-2xl")).toHaveCount(
    10,
    { timeout: 20_000 },
  );
  await expect(page.getByText("Demo data").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Forecast" })).toBeVisible();
  await expect(page.getByText(/Estimate with an 80 percent interval/)).toBeVisible();
  await settle(page);
  await axe(page, "light /app/platform/revenue");
  const first = page
    .getByRole("table", { name: "Customers" })
    .getByRole("row")
    .nth(1)
    .getByRole("button")
    .first();
  await first.click();
  await expect(page.getByRole("dialog")).toContainText("Subscriptions");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Table" }).first().click();
  await expect(page.getByRole("region", { name: /data table/ }).first()).toBeVisible();
});

test("analyst: upload wizard, then review decisions with keyboard shortcuts", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page, "analyst@demo.example");
  await page.goto("/app/suppliers");
  await page.getByRole("button", { name: "Upload suppliers" }).click();
  const csv =
    "Supplier Name,Town,State\nNorthgate Metals Corp,Pittsburgh,PA\nWillow Textile Co,Charlotte,NC\nUnknown Widgets LLC,Nowhere,ZZ\n";
  await page.setInputFiles("#upload-file", {
    name: "list.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await expect(page.getByText("Match each field to a column")).toBeVisible();
  await page.getByRole("button", { name: "Check the file" }).click();
  await expect(page.getByText(/rows are ready/)).toBeVisible();
  await page.getByRole("button", { name: /^Upload \d+ suppliers/ }).click();
  await expect(page.getByText("Upload complete")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("link", { name: "Willow Textile Co" }).first()).toBeVisible();

  await page.goto("/app/reviews");
  await expect(page.getByRole("heading", { name: /Record:/ })).toBeVisible();
  const before = await page
    .getByRole("navigation", { name: "Open reviews" })
    .getByRole("button")
    .count();
  expect(before).toBeGreaterThanOrEqual(2);
  await page.keyboard.press("j");
  await page.getByRole("button", { name: "Accept the top candidate" }).click();
  await expect(page.getByText("Decision saved")).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Open reviews" }).getByRole("button"),
  ).toHaveCount(before - 1);
  await page.getByRole("button", { name: "None of these" }).click();
  await expect(page.getByRole("dialog")).toContainText("Confirm this decision");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("The review queue is empty")).toBeVisible();
});

test("manager: alerts queue, drawer actions, a required dismissal reason, and a rule", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await login(page, "manager@demo.example");
  await page.goto("/app/alerts");
  const table = page.getByRole("table", { name: "Alerts" });
  await expect(table.getByRole("row")).not.toHaveCount(1);
  await table.getByRole("row").nth(1).getByRole("button").first().click();
  const drawer = page.getByRole("dialog");
  await drawer.getByRole("button", { name: "Acknowledged" }).click();
  await expect(page.getByText("Alert updated")).toBeVisible();
  await drawer.getByLabel("Add a comment").fill("Checked the source record.");
  await drawer.getByRole("button", { name: "Comment" }).click();
  await expect(drawer.getByText("Checked the source record.")).toBeVisible();
  await drawer.getByRole("button", { name: "Dismiss", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "Dismiss this alert" });
  await confirm.getByLabel("Reason").fill("Duplicate of an alert already worked.");
  await confirm.getByRole("button", { name: "Dismiss alert" }).click();
  await expect(drawer.getByText("Duplicate of an alert already worked.")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("tab", { name: "Rules" }).click();
  await page.getByRole("button", { name: "New rule" }).click();
  await page.getByLabel("Name").fill("Severe recalls");
  await page.getByLabel("Minimum severity (1 to 4)").selectOption("4");
  await page.getByLabel("Event types").fill("recall");
  await page.getByRole("button", { name: "Save rule" }).click();
  await expect(page.getByRole("cell", { name: "Severe recalls" })).toBeVisible();
});

test("manager: supplier profile, score breakdown, event evidence, and a correction request", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await login(page, "manager@demo.example");
  await page.goto("/app/suppliers");
  await page.getByLabel("Search by name").fill("Northgate Metals of Texas");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("link", { name: "Northgate Metals of Texas" })).toHaveCount(1);
  await page.getByRole("link", { name: "Northgate Metals of Texas" }).click();
  await expect(page).toHaveURL(/\/app\/suppliers\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Northgate Metals of Texas");
  await expect(page.getByRole("table", { name: "Score components" })).toBeVisible();
  await expect(page.getByText(/Risk signals are leads for human review/).first()).toBeVisible();
  await page.getByRole("tab", { name: "Events" }).click();
  await page
    .getByRole("link", { name: /OSHA inspection record: Northgate Metals of Texas/ })
    .first()
    .click();
  await expect(page.getByText("Final decision:")).toBeVisible();
  await expect(page.getByRole("table", { name: /Candidates considered/ })).toBeVisible();
  await expect(page.getByText("Reaches your suppliers")).toBeVisible();
  await page.getByRole("button", { name: "Request correction" }).click();
  await page
    .getByLabel("Details")
    .fill("The establishment named here belongs to a different company.");
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByText("Correction request sent")).toBeVisible();
  await page.goto("/app/events/5");
  await expect(page.locator("mark")).toContainText("Cobalt Ridge Logistics Co.");
});

test("manager: explorer draws a graph, finds a path, and shows concentration", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page, "manager@demo.example");
  await page.goto("/app/explorer");
  await page.getByLabel("Search a company").fill("northgate");
  await page.getByRole("button", { name: /Northgate Metals Corporation/ }).click();
  await expect(page.locator("canvas").first()).toBeVisible();
  await expect(page.getByText("In your portfolio", { exact: true })).toBeVisible();
  await page.getByLabel("From the selected company to").fill("northgate alloys");
  await page.getByRole("button", { name: /Northgate Alloys Ohio/ }).click();
  await expect(page.getByText(/Path found/)).toBeVisible();
  await page.getByRole("tab", { name: "Concentration" }).click();
  await expect(
    page.getByRole("heading", { name: "Concentration by ultimate parent" }),
  ).toBeVisible();
});

test("command palette searches suppliers and the theme choice persists", async ({ page }) => {
  await login(page, "manager@demo.example");
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox", { name: /Search suppliers/ }).fill("harborline");
  await page
    .getByRole("option", { name: /Harborline Foods/ })
    .first()
    .click();
  await expect(page).toHaveURL(/\/app\/suppliers\//);
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "Switch to light theme" })).toBeVisible();
});

test("an expired access token is renewed without signing the user out", async ({
  page,
  context,
}) => {
  await login(page, "manager@demo.example");
  await context.clearCookies({ name: "pr_access" });
  await page.goto("/app/suppliers");
  await expect(page.getByRole("heading", { name: "Suppliers" }).first()).toBeVisible();
  await expect(page.getByRole("table", { name: "Suppliers" })).toBeVisible();
});

test("tenant administrator: users, one-time API key, audit chain, risk configuration", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => localStorage.setItem("pr_cookie_notice", "1"));
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@demo.example");
  await page.getByLabel("Password").fill("Violet-Harbor-Quartz-7421");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Set up multi-factor sign-in" })).toBeVisible();
  const secret = ((await page.locator("p.font-mono").first().textContent()) ?? "").trim();
  await page.getByLabel("Six-digit code").fill(totp(secret));
  await page.getByRole("button", { name: "Verify and continue" }).click();
  await expect(page).toHaveURL(/\/app/);
  await page.goto("/app/admin");
  await page.getByLabel("Email").fill("new.analyst@demo.example");
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByText("Invitation sent")).toBeVisible();
  await page.getByRole("tab", { name: "API keys" }).click();
  await page.getByLabel("Name").fill("Reporting key");
  await page.getByRole("button", { name: "Create key" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "cannot be shown again" })).toContainText(
    "pk_",
  );
  await page.getByRole("button", { name: "I have stored it" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "cannot be shown again" })).toHaveCount(0);
  await page.getByRole("button", { name: "Revoke" }).first().click();
  await page.getByRole("button", { name: "Revoke key" }).click();
  await expect(page.getByText("Key revoked")).toBeVisible();
  await page.getByRole("tab", { name: "Audit log" }).click();
  await page.getByRole("button", { name: "Verify the hash chain" }).click();
  await expect(page.getByText(/Chain intact/)).toBeVisible();
  await page.getByRole("tab", { name: "Risk configuration" }).click();
  await expect(page.getByText(/Active configuration/)).toBeVisible();
  await page.goto("/app/billing");
  await expect(page.getByRole("heading", { name: "Billing" }).first()).toBeVisible();
  await expect(page.getByRole("meter")).toBeVisible();
  await axe(page, "light /app/billing");
  await page.goto("/app/admin");
  await settle(page);
  await axe(page, "light /app/admin");
});

test("a new alert reaches the open page through the live stream", async ({ page }) => {
  test.skip(!process.env.E2E_DB_URL, "E2E_DB_URL is not set (needs psql and the seeded database)");
  test.setTimeout(90_000);
  const streamOpened = page.waitForResponse((r) => r.url().includes("/stream/alerts"));
  await login(page, "manager@demo.example");
  await streamOpened;
  await page.waitForTimeout(1500); // the server subscribes right after it answers; events published earlier are not replayed
  await expect(page.getByRole("button", { name: /Notifications, 0 new/ })).toBeVisible();
  const { execFileSync } = await import("node:child_process");
  const sql = `WITH e AS (INSERT INTO events (source, source_id, event_type, severity, reported_at, title, summary, url, state)
    VALUES ('nhtsa', 'live-${Date.now()}', 'recall', 4, now(), 'NHTSA recall campaign: Harborline Foods, Inc.', 'Recall of a packaging component.', 'https://example.org/records/live', 'OH') RETURNING id)
    INSERT INTO event_entities (event_id, company_id, role, method, score, route)
    SELECT id, (SELECT id FROM companies WHERE canonical_name = 'Harborline Foods, Inc.'), 'operator', 'hybrid', 0.95, 'accepted' FROM e`;
  execFileSync(process.env.PSQL ?? "psql", [process.env.E2E_DB_URL!, "-c", sql]);
  const csrf = (await page.context().cookies()).find((c) => c.name === "pr_csrf")?.value ?? "";
  const r = await page.request.post("/api/v1/monitoring/recompute", {
    headers: { "X-CSRF-Token": csrf },
  });
  expect(r.ok()).toBeTruthy();
  await expect(page.getByText(/New alert: /).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: /Notifications, [1-9]\d* new/ })).toBeVisible();
});
