import { Check } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { CtaBand, PageHero, Section, SectionHead } from "@/components/marketing/blocks";
import { FaqSection } from "@/components/marketing/faq-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PRICING } from "@/lib/site";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Illustrative pricing for the demo environment: Starter, Professional, and Enterprise.",
  alternates: { canonical: "/pricing" },
};

const ROWS: [string, string, string, string][] = [
  ["Monitored suppliers included", "250", "2,500", "Sized to your portfolio"],
  ["Overage per 100 suppliers", "$40", "$120", "$300"],
  ["CSV upload and review queue", "Yes", "Yes", "Yes"],
  ["Regulator and news events", "Yes", "Yes", "Yes"],
  ["Corporate family roll-up", "View", "Alerts and roll-up", "Alerts and roll-up"],
  ["Email alerts", "Yes", "Yes", "Yes"],
  ["Webhooks and API keys", "No", "Yes", "Yes"],
  ["PDF supplier and portfolio reports", "No", "Yes", "Yes"],
  ["Audit log access", "No", "No", "Yes"],
  ["Mandatory multi-factor sign-in for administrators", "Yes", "Yes", "Yes"],
];

export default function PricingPage() {
  return (
    <>
      <PageHero
        eyebrow="Pricing"
        title="Plans sized by monitored suppliers"
        text="All figures are in US dollars."
      >
        <Badge tone="warning">{PRICING.label}</Badge>
      </PageHero>
      <Section>
        <div className="grid gap-6 lg:grid-cols-3">
          {PRICING.plans.map((p) => (
            <Card
              key={p.code}
              className={`flex flex-col p-7 ${p.code === "professional" ? "border-brand-500 ring-brand-500 ring-1" : ""}`}
            >
              <h2 className="text-h3">{p.name}</h2>
              <p className="mt-1 text-[15px] text-slate-700">{p.blurb}</p>
              <p className="text-ink mt-5 text-4xl font-semibold tracking-tight">${p.price}</p>
              <p className="text-sm text-slate-600">{p.unit}</p>
              <ul className="mt-6 flex-1 space-y-2">
                {p.features.map((f) => (
                  <li key={f} className="flex gap-3 text-[15px] text-slate-800">
                    <Check className="text-teal mt-1 size-4 shrink-0" aria-hidden />
                    {f}
                  </li>
                ))}
              </ul>
              <Button
                asChild
                variant={p.code === "professional" ? "primary" : "secondary"}
                className="mt-7"
              >
                <Link href="/contact">Request a demo</Link>
              </Button>
            </Card>
          ))}
        </div>
        <p className="mt-6 text-sm text-slate-600">
          {PRICING.annualNote} {PRICING.overageNote}
        </p>
      </Section>
      <Section tone="white">
        <SectionHead eyebrow="Compare" title="Feature comparison" />
        <div
          className="overflow-x-auto"
          tabIndex={0}
          role="region"
          aria-label="Table, scrolls horizontally on small screens"
        >
          <table className="w-full min-w-[640px] border-collapse text-left text-[15px]">
            <caption className="sr-only">Feature comparison of the three plans</caption>
            <thead>
              <tr className="border-line border-b">
                <th scope="col" className="text-ink py-3 pr-4 font-semibold">
                  Feature
                </th>
                {PRICING.plans.map((p) => (
                  <th key={p.code} scope="col" className="text-ink px-4 py-3 font-semibold">
                    {p.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r[0]} className="border-line border-b">
                  <th scope="row" className="py-3 pr-4 font-normal text-slate-800">
                    {r[0]}
                  </th>
                  <td className="px-4 py-3 text-slate-700">{r[1]}</td>
                  <td className="px-4 py-3 text-slate-700">{r[2]}</td>
                  <td className="px-4 py-3 text-slate-700">{r[3]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      <FaqSection
        items={[
          {
            q: "Are these real prices?",
            a: "No. The prices on this page are illustrative and belong to the demo environment. No payment is collected.",
          },
          {
            q: "What counts as a monitored supplier?",
            a: "A supplier row in your portfolio. In the demo price list the limit is compared with the number of supplier rows.",
          },
          {
            q: "How does overage work?",
            a: "Monitored suppliers above the plan limit are billed per block of 100 at the overage rate shown for the plan.",
          },
          {
            q: "Is there an annual discount?",
            a: "Annual billing is discounted by 10 percent in the demo price list.",
          },
          {
            q: "Which plan includes the API?",
            a: "API keys are included from Professional. Starter users can upload CSV files in the application.",
          },
        ]}
      />
      <CtaBand />
    </>
  );
}
