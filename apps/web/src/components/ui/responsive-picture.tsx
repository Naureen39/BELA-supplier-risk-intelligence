export interface PictureManifestEntry {
  width: number;
  height: number;
  variants: { file: string; width: number; format: "avif" | "webp" }[];
}

/** Serves the AVIF and WebP variants produced by `npm run images`, with explicit dimensions to avoid layout shift. */
export function ResponsivePicture({
  entry,
  name,
  alt,
  sizes = "(min-width: 1280px) 1120px, 100vw",
  priority = false,
  className,
}: {
  entry: PictureManifestEntry;
  name: string;
  alt: string;
  sizes?: string;
  priority?: boolean;
  className?: string;
}) {
  const set = (fmt: "avif" | "webp") =>
    entry.variants
      .filter((v) => v.format === fmt)
      .map((v) => `/images/optimized/${v.file} ${v.width}w`)
      .join(", ");
  const fallback = entry.variants.filter((v) => v.format === "webp").at(-1);
  return (
    <picture>
      <source type="image/avif" srcSet={set("avif")} sizes={sizes} />
      <source type="image/webp" srcSet={set("webp")} sizes={sizes} />
      <img
        src={`/images/optimized/${fallback?.file ?? `${name}.webp`}`}
        width={entry.width}
        height={entry.height}
        alt={alt}
        loading={priority ? "eager" : "lazy"}
        decoding="async"
        className={className}
      />
    </picture>
  );
}
