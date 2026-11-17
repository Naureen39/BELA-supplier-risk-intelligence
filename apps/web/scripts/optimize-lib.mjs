import { mkdir, readdir, writeFile } from "node:fs/promises";
import { basename, extname, join } from "node:path";
import sharp from "sharp";

export const WIDTHS = [640, 1024, 1600, 2400];
export const FORMATS = ["avif", "webp"];

/** Convert every JPEG and PNG in `src` to AVIF and WebP at responsive widths. Never upscales. */
export async function optimizeImages(src, dest) {
  await mkdir(dest, { recursive: true });
  const manifest = {};
  for (const file of (await readdir(src)).sort()) {
    if (!/\.(jpe?g|png)$/i.test(file)) continue;
    const name = basename(file, extname(file));
    const meta = await sharp(join(src, file)).metadata();
    const widths = WIDTHS.filter((w) => w <= (meta.width ?? 0));
    if (!widths.length && meta.width) widths.push(meta.width);
    const variants = [];
    for (const w of widths) {
      for (const format of FORMATS) {
        const out = `${name}-${w}.${format}`;
        await sharp(join(src, file))
          .resize({ width: w, withoutEnlargement: true })
          [format]({ quality: format === "avif" ? 50 : 78 })
          .toFile(join(dest, out));
        variants.push({ file: out, width: w, format });
      }
    }
    manifest[name] = { width: meta.width, height: meta.height, variants };
  }
  await writeFile(join(dest, "manifest.json"), JSON.stringify(manifest, null, 2));
  return manifest;
}
