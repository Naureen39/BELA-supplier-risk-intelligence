// Runs Lighthouse (desktop preset) against a running site and saves reports to docs/quality.
// Usage: node scripts/quality.mjs [baseUrl]   (the site must be built and started first)
import { launch } from "chrome-launcher";
import lighthouse from "lighthouse";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.argv[2] ?? "http://127.0.0.1:3000";
const out = join(dirname(fileURLToPath(import.meta.url)), "../../../docs/quality");
mkdirSync(out, { recursive: true });
const PAGES = [
  ["home", "/"],
  ["pricing", "/pricing"],
  ["platform", "/platform"],
  ["article", "/resources/measuring-a-matching-system"],
  ["login", "/login"],
];

const chrome = await launch({ chromeFlags: ["--headless=new", "--no-sandbox"] });
const summary = {};
try {
  for (const [name, path] of PAGES) {
    const run = await lighthouse(
      `${base}${path}`,
      {
        port: chrome.port,
        output: ["json", "html"],
        logLevel: "error",
        onlyCategories: ["performance", "accessibility", "best-practices", "seo"],
      },
      {
        extends: "lighthouse:default",
        settings: {
          formFactor: "desktop",
          screenEmulation: {
            mobile: false,
            width: 1350,
            height: 940,
            deviceScaleFactor: 1,
            disabled: false,
          },
          throttlingMethod: "simulate",
          throttling: { rttMs: 40, throughputKbps: 10240, cpuSlowdownMultiplier: 1 },
        },
      },
    );
    const [json, html] = run.report;
    writeFileSync(join(out, `lighthouse-${name}.json`), json);
    writeFileSync(join(out, `lighthouse-${name}.html`), html);
    const c = run.lhr.categories;
    const a = run.lhr.audits;
    summary[name] = {
      url: `${base}${path}`,
      performance: Math.round((c.performance.score ?? 0) * 100),
      accessibility: Math.round((c.accessibility.score ?? 0) * 100),
      bestPractices: Math.round((c["best-practices"].score ?? 0) * 100),
      seo: Math.round((c.seo.score ?? 0) * 100),
      lcpMs: Math.round(a["largest-contentful-paint"].numericValue ?? 0),
      cls: Number((a["cumulative-layout-shift"].numericValue ?? 0).toFixed(4)),
      tbtMs: Math.round(a["total-blocking-time"].numericValue ?? 0),
    };
    console.log(name, JSON.stringify(summary[name]));
  }
} finally {
  await chrome.kill();
}
writeFileSync(
  join(out, "lighthouse-summary.json"),
  JSON.stringify(
    { preset: "desktop", generated: new Date().toISOString().slice(0, 10), pages: summary },
    null,
    2,
  ),
);
