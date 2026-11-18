import { defineConfig, devices } from "@playwright/test";

// The full suite runs in Chrome. Firefox and WebKit (the engine behind Safari) run the read-only checks:
// accessibility on every marketing page and the cross-browser spec. Edge shares Chrome's engine and is not
// installed here, so it is not run (see docs/quality_review.md).
const readOnly = ["**/cross-browser.spec.ts", "**/a11y.spec.ts"];

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "reports/e2e.json" }]],
  use: {
    baseURL: process.env.WEB_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chrome",
      use: { ...devices["Desktop Chrome"], channel: process.env.PW_CHANNEL ?? "chrome" },
      testIgnore: ["**/cross-browser.spec.ts"],
    },
    { name: "firefox", use: { ...devices["Desktop Firefox"] }, testMatch: readOnly },
    { name: "webkit", use: { ...devices["Desktop Safari"] }, testMatch: readOnly },
  ],
  webServer: {
    command: "npx next start -p 3000",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    env: { API_ORIGIN: process.env.API_ORIGIN ?? "http://127.0.0.1:8000" },
  },
});
