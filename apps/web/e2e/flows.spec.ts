import { createHmac } from "node:crypto";
import { expect, test } from "@playwright/test";

const PASSWORD = "Violet-Harbor-Quartz-7421";

function totp(secret: string): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/=+$/, "").toUpperCase())
    bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const bytes = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = createHmac("sha1", bytes).update(counter).digest();
  const o = h[h.length - 1]! & 15;
  const code =
    (((h[o]! & 127) << 24) | (h[o + 1]! << 16) | (h[o + 2]! << 8) | h[o + 3]!) % 1_000_000;
  return String(code).padStart(6, "0");
}

test("sign in as a manager lands on /app", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("manager@demo.example");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText("manager@demo.example")).toBeVisible();
  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "pr_access");
  expect(access?.httpOnly).toBe(true);
  expect(cookies.find((c) => c.name === "pr_csrf")?.httpOnly).toBe(false);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/app");
  await expect(page).toHaveURL(/\/login$/);
});

test("wrong password shows one generic message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("manager@demo.example");
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("administrator enrolls multi-factor sign-in, then signs in with a code", async ({
  page,
  context,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@demo.example");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Set up multi-factor sign-in" })).toBeVisible();
  const secret = (await page.locator("p.font-mono").first().textContent())!.trim();
  await page.getByLabel("Six-digit code").fill(totp(secret));
  await page.getByRole("button", { name: "Verify and continue" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await context.clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@demo.example");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByLabel("Six-digit code")).toBeVisible();
  await page.getByRole("button", { name: "Use a recovery code" }).click();
  await expect(page.getByLabel("Recovery code")).toBeVisible();
});

test("password reset flow", async ({ page }) => {
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill("anyone@example.org");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If the account exists");
  await page.goto("/reset-password?token=e2e-reset-token-0123456789");
  await page.getByLabel("New password", { exact: true }).fill("Maple-Anchor-Lantern-9183");
  await page.getByLabel("Confirm password").fill("Maple-Anchor-Lantern-9183");
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByText("The password has been changed")).toBeVisible();
  await page.goto("/login");
  await page.getByLabel("Email").fill("reset@demo.example");
  await page.getByLabel("Password").fill("Maple-Anchor-Lantern-9183");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
});

test("demo request is validated and submitted", async ({ page }) => {
  await page.goto("/contact");
  await page.getByRole("button", { name: "Request a demo" }).click();
  await expect(page.getByText("Enter your name")).toBeVisible();
  await expect(page.getByText("Consent is required")).toBeVisible();
  await page.getByLabel("Name").fill("Alex Morgan");
  await page.getByLabel("Work email").fill("alex@example.org");
  await page.getByLabel("Organization").fill("Example Supply Co");
  await page.getByLabel("Message (optional)").fill("We would like to see the review workflow.");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Request a demo" }).click();
  await expect(page).toHaveURL(/\/contact\/thanks$/);
});

test("home call to action prefills the contact form", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Work email").fill("prefill@example.org");
  await page.getByRole("button", { name: "Request a demo" }).last().click();
  await expect(page).toHaveURL(/\/contact\?email=prefill%40example\.org/);
  await expect(page.getByLabel("Work email")).toHaveValue("prefill@example.org");
});

test("newsletter subscription asks for confirmation", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Insights by email" }).fill("reader@example.org");
  await page.getByRole("button", { name: "Subscribe" }).click();
  await expect(page.getByRole("status").filter({ hasText: "confirmation email" })).toBeVisible();
});

test("newsletter confirmation rejects an invalid token", async ({ page }) => {
  await page.goto("/newsletter/confirm?token=invalid-token-0000000000");
  await expect(page.getByRole("heading", { name: "This link is not valid" })).toBeVisible();
});

test("article filter by tag", async ({ page }) => {
  await page.goto("/resources");
  await expect(page.getByRole("listitem").filter({ hasText: "min read" })).toHaveCount(6);
  await page.getByRole("button", { name: "Evaluation" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "min read" })).toHaveCount(1);
});
