import { SOLUTIONS, solutionBySlug } from "@/content/solutions";
import { OG_SIZE, ogImage } from "@/lib/og";

export const size = OG_SIZE;
export const contentType = "image/png";
export function generateStaticParams() {
  return SOLUTIONS.map((s) => ({ slug: s.slug }));
}

export const alt = "Solution preview";

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const s = solutionBySlug((await params).slug);
  return ogImage(s?.headline ?? "Solutions", s?.name ?? "Solutions");
}
