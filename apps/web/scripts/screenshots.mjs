// Capture screenshots of the marketing site (and, when credentials are given, the application) with Playwright.
//   WEB_URL=http://127.0.0.1:3000 node scripts/screenshots.mjs [outDir]
//   APP_EMAIL=manager@demo.example APP_PASSWORD=... node scripts/screenshots.mjs   # adds application pages
// Run against a running site (npm run build && npm start, or the compose stack). Output defaults to ../../docs/screenshots.
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const base = process.env.WEB_URL ?? "http://127.0.0.1:3000";
const out = process.argv[2] ?? fileURLToPath(new URL("../../../docs/screenshots", import.meta.url));

const MARKETING = [
  ["home", "/"],
  ["platform", "/platform"],
  ["pricing", "/pricing"],
  ["security", "/security"],
  ["developers", "/developers"],
  ["methodology", "/methodology"],
  ["solutions-procurement", "/solutions/procurement-and-supply-chain"],
  ["industries-automotive", "/industries/automotive"],
  ["resources", "/resources"],
  ["contact", "/contact"],
  ["login", "/login"],
];
const APP = [
  ["app-overview", "/app"],
  ["app-suppliers", "/app/suppliers"],
  ["app-review", "/app/reviews"],
  ["app-alerts", "/app/alerts"],
  ["app-graph", "/app/explorer"],
  ["app-analytics", "/app/analytics"],
];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL });
await mkdir(out, { recursive: true });
let count = 0;

async function shoot(page, name, path, full) {
  await page.goto(base + path, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  // Reveal-on-scroll content: scroll through the page once so every section has appeared.
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 600) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 40));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: full });
  count += 1;
}

// Marketing pages: desktop full page, plus the home page on a phone.
const desktop = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  reducedMotion: "reduce",
});
const page = await desktop.newPage();
for (const [name, path] of MARKETING) await shoot(page, name, path, true);

const phone = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  reducedMotion: "reduce",
});
await shoot(await phone.newPage(), "home-mobile", "/", false);

if (process.env.APP_EMAIL && process.env.APP_PASSWORD) {
  const r = await desktop.request.post(`${base}/api/v1/auth/login`, {
    data: { email: process.env.APP_EMAIL, password: process.env.APP_PASSWORD },
  });
  if (!r.ok()) throw new Error(`application sign-in failed: HTTP ${r.status()}`);
  for (const [name, path] of APP) await shoot(page, name, path, false);
}

await browser.close();
console.log(`${count} screenshots written to ${out}`);
