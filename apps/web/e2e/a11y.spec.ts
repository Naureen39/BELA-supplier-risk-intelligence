import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { PAGES } from "./pages";

const results: Record<string, unknown> = {};

for (const width of [375, 1280]) {
  for (const path of PAGES) {
    test(`axe ${width}px ${path}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const r = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
        .analyze();
      results[`${width} ${path}`] = {
        violations: r.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          nodes: v.nodes.length,
        })),
        passes: r.passes.length,
      };
      expect(
        r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`),
      ).toEqual([]);
    });
  }
}

test.afterAll(() => {
  mkdirSync("reports", { recursive: true });
  writeFileSync("reports/axe.json", JSON.stringify(results, null, 2));
});
