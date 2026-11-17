import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "reports/e2e.json" }]],
  use: {
    baseURL: process.env.WEB_URL ?? "http://127.0.0.1:3000",
    channel: process.env.PW_CHANNEL ?? "chrome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npx next start -p 3000",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    env: { API_ORIGIN: process.env.API_ORIGIN ?? "http://127.0.0.1:8000" },
  },
});
