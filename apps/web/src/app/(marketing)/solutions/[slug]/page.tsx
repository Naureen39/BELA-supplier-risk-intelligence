import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CtaBand, PageHero, Section, SectionHead } from "@/components/marketing/blocks";
import { FaqSection } from "@/components/marketing/faq-section";
import { ProductMock } from "@/components/marketing/product-mock";
import { Card } from "@/components/ui/card";
import { SOLUTIONS, solutionBySlug } from "@/content/solutions";

export const dynamicParams = false;
export function generateStaticParams() {
  return SOLUTIONS.map((s) => ({ slug: s.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const s = solutionBySlug((await params).slug);
  return s
    ? { title: s.name, description: s.headline, alternates: { canonical: `/solutions/${s.slug}` } }
    : {};
}

export default async function SolutionPage({ params }: { params: Promise<{ slug: string }> }) {
  const s = solutionBySlug((await params).slug);
  if (!s) notFound();
  return (
    <>
      <PageHero eyebrow={`Solutions / ${s.name}`} title={s.headline} />
      <Section>
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <SectionHead eyebrow="The problem" title="Where the work breaks down" />
            <p className="-mt-6 text-[17px] leading-8 text-slate-700">{s.problem}</p>
          </div>
          <div>
            <SectionHead eyebrow="Approach" title="How the platform helps" />
            <ul className="-mt-6 space-y-3">
              {s.approach.map((a) => (
                <li
                  key={a}
                  className="border-line rounded-[12px] border bg-white p-4 text-[16px] leading-7 text-slate-800"
                >
                  {a}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>
      <Section tone="white">
        <SectionHead eyebrow="Workflow" title="A typical path through the product" />
        <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.1fr]">
          <ol className="space-y-3">
            {s.workflow.map((w, n) => (
              <li key={w} className="flex gap-4">
                <span className="bg-brand-100 text-brand-600 flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
                  {n + 1}
                </span>
                <span className="pt-0.5 text-[16px] text-slate-800">{w}</span>
              </li>
            ))}
          </ol>
          <ProductMock variant={s.slug.startsWith("esg") ? "family" : "review"} />
        </div>
      </Section>
      <Section>
        <SectionHead
          eyebrow="Outcomes"
          title="How outcomes are measured"
          text="The platform reports measurements from the evaluation set, labeled with the data they come from. This page does not quote results that have not been measured."
        />
        <div className="grid gap-6 md:grid-cols-3">
          {s.measures.map((m) => (
            <Card key={m.metric} className="p-6">
              <h3 className="text-h4">{m.metric}</h3>
              <p className="mt-2 text-[15px] leading-7 text-slate-700">{m.text}</p>
            </Card>
          ))}
        </div>
      </Section>
      <FaqSection items={s.faq} />
      <CtaBand />
    </>
  );
}
