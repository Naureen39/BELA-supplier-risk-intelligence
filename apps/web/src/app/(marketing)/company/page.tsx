import type { Metadata } from "next";
import { PageHero, Section, SectionHead } from "@/components/marketing/blocks";
import { Card } from "@/components/ui/card";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Company",
  description: "Mission, approach to responsible use, principles, and contact details.",
  alternates: { canonical: "/company" },
};

export default function CompanyPage() {
  return (
    <>
      <PageHero
        eyebrow="Company"
        title="Make public records about suppliers easier to find and safer to use"
        text="Provenance Risk is a demonstration product that connects public records to the companies in a supply base."
      />
      <Section>
        <SectionHead eyebrow="Principles" title="How the product is built" />
        <div className="grid gap-6 md:grid-cols-2">
          {[
            {
              t: "Evidence over assertion",
              p: "Every event links to its source with a date. Every claim on this site rests on a measurement or a public source.",
            },
            {
              t: "Records are not verdicts",
              p: "The product states what a record says. It does not state that a company broke a law or caused an incident.",
            },
            {
              t: "People decide",
              p: "Uncertain matches and alerts go to a person, and the person's reasoning is recorded.",
            },
            {
              t: "State the limits",
              p: "Coverage, model status, and measurement gaps are written on the page where they apply.",
            },
          ].map((x) => (
            <Card key={x.t} className="p-6">
              <h3 className="text-h4">{x.t}</h3>
              <p className="mt-2 text-[15px] leading-7 text-slate-700">{x.p}</p>
            </Card>
          ))}
        </div>
      </Section>
      <Section tone="white">
        <SectionHead eyebrow="Contact" title="Get in touch" />
        <dl className="space-y-3 text-[16px]">
          <div>
            <dt className="text-ink font-medium">General and demonstration requests</dt>
            <dd className="text-slate-700">
              <a
                href={`mailto:${SITE.email}`}
                className="text-brand-600 underline underline-offset-2"
              >
                {SITE.email}
              </a>
              , or use the{" "}
              <a href="/contact" className="text-brand-600 underline underline-offset-2">
                contact form
              </a>
              .
            </dd>
          </div>
          <div>
            <dt className="text-ink font-medium">Security reports</dt>
            <dd className="text-slate-700">
              Use the same address and mark the subject as security. Do not include customer data.
            </dd>
          </div>
        </dl>
        <p className="mt-6 text-sm text-slate-600">
          The address uses a reserved example domain because this is a demonstration environment.
        </p>
      </Section>
    </>
  );
}
