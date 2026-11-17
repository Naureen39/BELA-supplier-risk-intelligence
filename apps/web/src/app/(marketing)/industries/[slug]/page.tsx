import { Check } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CtaBand, PageHero, Section, SectionHead } from "@/components/marketing/blocks";
import { FaqSection } from "@/components/marketing/faq-section";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Breadcrumbs } from "@/components/ui/breadcrumbs";
import { bySlug, INDUSTRIES } from "@/content/industries";

export const dynamicParams = false;
export function generateStaticParams() {
  return INDUSTRIES.map((i) => ({ slug: i.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const i = bySlug((await params).slug);
  return i
    ? {
        title: `${i.name} supplier risk`,
        description: i.card,
        alternates: { canonical: `/industries/${i.slug}` },
      }
    : {};
}

export default async function IndustryPage({ params }: { params: Promise<{ slug: string }> }) {
  const i = bySlug((await params).slug);
  if (!i) notFound();
  return (
    <>
      <PageHero
        eyebrow={`Industries / ${i.name}`}
        title={`${i.name}: supplier risk from public records`}
        text={i.intro}
      >
        <Breadcrumbs items={[{ title: "Industries" }, { title: i.name }]} />
      </PageHero>
      <Section>
        <SectionHead eyebrow="Typical risk themes" title="Records that matter in this sector" />
        <div className="grid gap-6 md:grid-cols-3">
          {i.themes.map((t) => (
            <Card key={t.title} className="p-6">
              <h3 className="text-h4">{t.title}</h3>
              <p className="mt-2 text-[15px] leading-7 text-slate-700">{t.text}</p>
              <p className="mt-3 text-sm text-slate-600">Source: {t.source}</p>
            </Card>
          ))}
        </div>
      </Section>
      <Section tone="white">
        <div className="border-line rounded-[12px] border bg-slate-50 p-8">
          <Badge tone="brand">Illustrative scenario</Badge>
          <h2 className="text-h3 mt-3">{i.scenario.title}</h2>
          <p className="mt-3 max-w-3xl text-[17px] leading-8 text-slate-700">{i.scenario.text}</p>
        </div>
      </Section>
      <Section>
        <SectionHead
          eyebrow="Recommended workflow"
          title="How teams in this sector typically work"
        />
        <ol className="space-y-3">
          {i.workflow.map((w, n) => (
            <li key={w} className="border-line flex gap-4 rounded-[12px] border bg-white p-4">
              <span className="bg-brand-100 text-brand-600 flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
                {n + 1}
              </span>
              <span className="pt-0.5 text-[16px] text-slate-800">{w}</span>
            </li>
          ))}
        </ol>
        <div className="mt-10 flex flex-wrap gap-3">
          {i.related.map((r) => (
            <Link
              key={r.href}
              href={r.href}
              className="border-line text-ink inline-flex items-center gap-2 rounded-full border bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
            >
              <Check className="text-teal size-4" aria-hidden /> {r.title}
            </Link>
          ))}
        </div>
      </Section>
      <FaqSection items={i.faq} />
      <CtaBand />
    </>
  );
}
