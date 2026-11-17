import { mkdirSync, mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import sharp from "sharp";
import { expect, it } from "vitest";
// @ts-expect-error plain JavaScript module without type declarations
import { optimizeImages } from "../scripts/optimize-lib.mjs";

it("writes AVIF and WebP variants without upscaling, and a manifest", async () => {
  const dir = mkdtempSync(join(tmpdir(), "img-"));
  const src = join(dir, "src");
  const out = join(dir, "out");
  mkdirSync(src);
  await sharp({ create: { width: 1200, height: 600, channels: 3, background: "#2f74d8" } })
    .jpeg()
    .toFile(join(src, "hero.jpg"));
  const manifest = await optimizeImages(src, out);
  expect(manifest.hero.width).toBe(1200);
  expect(
    manifest.hero.variants
      .map((v: { width: number }) => v.width)
      .sort((a: number, b: number) => a - b),
  ).toEqual([640, 640, 1024, 1024]);
  const files = readdirSync(out).sort();
  expect(files).toContain("hero-640.avif");
  expect(files).toContain("hero-1024.webp");
  expect(files.some((f) => f.includes("1600"))).toBe(false);
  expect((await sharp(join(out, "hero-640.webp")).metadata()).width).toBe(640);
  expect(JSON.parse(readFileSync(join(out, "manifest.json"), "utf8")).hero.height).toBe(600);
}, 30000);
