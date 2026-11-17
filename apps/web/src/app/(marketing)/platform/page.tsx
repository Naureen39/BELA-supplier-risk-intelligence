import { Check } from "lucide-react";
import type { Metadata } from "next";
import { CtaBand, PageHero, Section } from "@/components/marketing/blocks";
import { ProductMock } from "@/components/marketing/product-mock";

export const metadata: Metadata = {
  title: "Platform",
  description:
    "Resolution, corporate family, events, risk scoring, monitoring, and API in one pipeline.",
  alternates: { canonical: "/platform" },
};

const MODULES = [
  {
    id: "resolution",
    title: "Resolution",
    variant: "review" as const,
    text: "Uploaded rows and regulator records are matched to canonical companies. Identifiers decide first. Names are scored with supporting attributes, and the result is routed to accept, review, or unresolved.",
    points: [
      "Normalization, blocking, retrieval, and probabilistic scoring",
      "Every candidate, score, and route is stored",
      "Side-by-side review with bulk accept and a not-in-database outcome",
      "Duplicate suppliers can be merged and unmerged",
    ],
  },
  {
    id: "family",
    title: "Corporate family",
    variant: "family" as const,
    text: "Ownership edges from public filings and registries connect facilities, subsidiaries, and parents. Each edge shows its source and as-of date.",
    points: [
      "GLEIF, SEC Exhibit 21, and Wikidata as sources",
      "Neighbor expansion and shortest path between companies",
      "Concentration view: suppliers per ultimate parent",
      "Portfolio overlay on the graph",
    ],
  },
  {
    id: "events",
    title: "Events",
    variant: "profile" as const,
    text: "Regulator records and news mentions are normalized to one schema, de-duplicated across sources, and linked to companies with a stored confidence.",
    points: [
      "EPA, OSHA, NHTSA, CPSC, and FDA normalizers",
      "News mentions linked and classified, with a degraded mode when a model is unavailable",
      "Links below the accept threshold go to a review queue",
      "Original record linked from every event",
    ],
  },
  {
    id: "risk",
    title: "Risk scoring",
    variant: "profile" as const,
    text: "A score combines event impacts. Each impact is the product of severity, recency, link confidence, relationship weight, and source reliability, and impacts are capped before they are combined.",
    points: [
      "Every component visible with its event and weights",
      "Versioned configuration with tenant bounds",
      "Levels: low, medium, high, critical",
      "Roll-up through the corporate family at a lower weight",
    ],
  },
  {
    id: "monitoring",
    title: "Monitoring",
    variant: "analytics" as const,
    text: "New records are matched to your suppliers and their families. Alerts follow rules you set and are delivered in the application, by email, and by webhook.",
    points: [
      "Alert lifecycle with assignment, comments, and a required dismissal reason",
      "Rules by event type, severity, tier, and state",
      "Live alert stream for the application",
      "Delivery log for every notification",
    ],
  },
];

export default function PlatformPage() {
  return (
    <>
      <PageHero
        eyebrow="Platform"
        title="One pipeline from supplier name to monitored risk"
        text="Each stage keeps its evidence, so a person can check how a supplier came to be linked to a record."
      />
      <Section tone="white">
        <ol aria-label="Pipeline" className="grid gap-3 text-center sm:grid-cols-5">
          {[
            "Supplier lists and records",
            "Resolve",
            "Corporate family",
            "Events and risk",
            "Alerts and reports",
          ].map((s, i) => (
            <li
              key={s}
              className="border-line text-ink relative rounded-[12px] border bg-slate-50 px-3 py-5 text-[15px] font-medium"
            >
              <span className="text-brand-600 mb-1 block text-xs font-semibold">Step {i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
      </Section>
      {MODULES.map((m, i) => (
        <Section key={m.id} id={m.id} tone={i % 2 ? "white" : "page"}>
          <div
            className={`grid items-center gap-10 lg:grid-cols-2 ${i % 2 ? "lg:[&>*:first-child]:order-2" : ""}`}
          >
            <div>
              <h2 className="text-h2">{m.title}</h2>
              <p className="mt-4 text-[17px] leading-8 text-slate-700">{m.text}</p>
              <ul className="mt-6 space-y-2">
                {m.points.map((p) => (
                  <li key={p} className="flex gap-3 text-[16px] text-slate-800">
                    <Check className="text-teal mt-1 size-4 shrink-0" aria-hidden />
                    {p}
                  </li>
                ))}
              </ul>
            </div>
            <ProductMock variant={m.variant} />
          </div>
        </Section>
      ))}
      <CtaBand />
    </>
  );
}
