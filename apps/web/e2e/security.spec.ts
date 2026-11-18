import { expect, test, type Page } from "@playwright/test";
import { login, settle } from "./helpers";
import { PAGES } from "./pages";

async function collectViolations(page: Page): Promise<() => Promise<string[]>> {
  const consoleMsgs: string[] = [];
  page.on("console", (m) => {
    if (/Content Security Policy|Refused to/i.test(m.text())) consoleMsgs.push(m.text());
  });
  await page.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      (window as unknown as { __csp: string[] }).__csp.push(
        `${e.violatedDirective} ${e.blockedURI}`,
      );
    });
  });
  return async () => [
    ...consoleMsgs,
    ...(await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp)),
  ];
}

test("the content security policy blocks nothing the site needs, on every marketing page", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const violations = await collectViolations(page);
  const seen: string[] = [];
  for (const path of PAGES.filter((p) => !p.startsWith("/reset-password"))) {
    await page.goto(path);
    await page.waitForLoadState("load");
    seen.push(...(await violations()).map((v) => `${path}: ${v}`));
  }
  expect(seen).toEqual([]);
});

test("the content security policy blocks nothing on the application pages, charts and graph included", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const violations = await collectViolations(page);
  await login(page, "manager@demo.example");
  const seen: string[] = [];
  for (const path of [
    "/app",
    "/app/analytics",
    "/app/explorer?company=1",
    "/app/suppliers",
    "/app/events/1",
    "/app/alerts",
    "/app/reviews",
  ]) {
    await page.goto(path);
    await settle(page);
    seen.push(...(await violations()).map((v) => `${path}: ${v}`));
  }
  expect(seen).toEqual([]);
});

test("an injected inline handler cannot reach other origins (connect-src and form-action are self)", async ({
  page,
}) => {
  await page.goto("/");
  const blocked = await page.evaluate(async () => {
    try {
      await fetch("https://example.org/", { mode: "no-cors" });
      return false;
    } catch {
      return true;
    }
  });
  expect(blocked).toBe(true);
});

test("pages cannot be framed", async ({ page }) => {
  await page.goto("/");
  const framed = await page.evaluate(
    () =>
      new Promise<boolean>((resolve) => {
        const f = document.createElement("iframe");
        f.src = "/";
        f.onload = () => {
          try {
            resolve(!!f.contentDocument?.body?.innerHTML);
          } catch {
            resolve(false);
          }
        };
        f.onerror = () => resolve(false);
        document.body.appendChild(f);
        setTimeout(() => resolve(false), 3000);
      }),
  );
  expect(framed).toBe(false);
});

test("the API refuses cookie-authenticated writes without the CSRF header, and sets strict cookies", async ({
  page,
  request,
}) => {
  await login(page, "manager@demo.example");
  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "pr_access");
  expect(access?.httpOnly).toBe(true);
  expect(access?.sameSite).toBe("Strict");
  const noCsrf = await page.request.post("/api/v1/suppliers", { data: { name: "No Csrf Test" } });
  expect(noCsrf.status()).toBe(403);
  const unauth = await request.get("/api/v1/suppliers");
  expect(unauth.status()).toBe(401);
  const headers = unauth.headers();
  expect(headers["cache-control"]).toContain("no-store");
  expect(headers["x-content-type-options"]).toBe("nosniff");
});
