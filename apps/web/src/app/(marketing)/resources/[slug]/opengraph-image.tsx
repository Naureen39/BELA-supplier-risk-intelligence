import { ARTICLES } from "@/lib/articles";
import { OG_SIZE, ogImage } from "@/lib/og";

export const size = OG_SIZE;
export const contentType = "image/png";
export function generateStaticParams() {
  return ARTICLES.map((a) => ({ slug: a.slug }));
}

export const alt = "Article preview";

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const a = ARTICLES.find((x) => x.slug === slug);
  return ogImage(a?.title ?? "Insights", a?.tag ?? "Resources");
}
