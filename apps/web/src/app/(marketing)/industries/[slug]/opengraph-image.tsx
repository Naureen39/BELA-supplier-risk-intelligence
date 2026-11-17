import { bySlug, INDUSTRIES } from "@/content/industries";
import { OG_SIZE, ogImage } from "@/lib/og";

export const size = OG_SIZE;
export const contentType = "image/png";
export function generateStaticParams() {
  return INDUSTRIES.map((i) => ({ slug: i.slug }));
}

export const alt = "Industry preview";

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const i = bySlug((await params).slug);
  return ogImage(i ? `${i.name}: supplier risk from public records` : "Industries", "Industries");
}
