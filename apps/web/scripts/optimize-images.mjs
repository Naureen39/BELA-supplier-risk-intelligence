// Usage: npm run images
// Reads public/images/source/*.{jpg,png}, writes AVIF and WebP at 640, 1024, 1600, and 2400 px to
// public/images/optimized, and a manifest.json for the <ResponsivePicture> component.
// Record the photographer and source URL of every photograph in public/images/CREDITS.md.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { optimizeImages } from "./optimize-lib.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "../public/images");
const manifest = await optimizeImages(join(root, "source"), join(root, "optimized"));
console.log(`${Object.keys(manifest).length} image(s) optimized`);
