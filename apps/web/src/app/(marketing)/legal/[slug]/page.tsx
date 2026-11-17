import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageHero, Section } from "@/components/marketing/blocks";
import { LEGAL, legalBySlug } from "@/content/legal";

export const dynamicParams = false;
export function generateStaticParams() {
  return LEGAL.map((d) => ({ slug: d.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const d = legalBySlug((await params).slug);
  return d ? { title: d.title, alternates: { canonical: `/legal/${d.slug}` } } : {};
}

export default async function LegalPage({ params }: { params: Promise<{ slug: string }> }) {
  const d = legalBySlug((await params).slug);
  if (!d) notFound();
  return (
    <>
      <PageHero eyebrow="Legal" title={d.title} text={d.intro} />
      <Section>
        <div className="max-w-3xl">
          <p className="mb-8 text-sm text-slate-600">
            Last updated <time dateTime={d.updated}>{d.updated}</time>
          </p>
          {d.sections.map((s) => (
            <section key={s.heading} className="mb-8">
              <h2 className="text-h4 mb-3">{s.heading}</h2>
              {s.body.map((p) => (
                <p key={p} className="mb-3 text-[16px] leading-7 text-slate-700">
                  {p}
                </p>
              ))}
            </section>
          ))}
        </div>
      </Section>
    </>
  );
}
