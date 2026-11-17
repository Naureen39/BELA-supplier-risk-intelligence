import type { Metadata } from "next";
import { PageHero, Section, SectionHead } from "@/components/marketing/blocks";
import { Card } from "@/components/ui/card";
import { fmt, getStats, SOURCE_LABELS } from "@/lib/stats";

export const revalidate = 3600;
export const metadata: Metadata = {
  title: "Methodology",
  description:
    "Data sources and terms, coverage limits, models, evaluation design, results, limitations, and the correction process.",
  alternates: { canonical: "/methodology" },
};

const SOURCES: [string, string, string][] = [
  [
    "SEC EDGAR",
    "Company identifiers (CIK), filings, Exhibit 21 subsidiary lists",
    "Public filings. The SEC fair access policy applies.",
  ],
  ["GLEIF", "Legal Entity Identifiers and relationship records", "CC0 1.0"],
  ["Wikidata", "Company entities, identifiers, and ownership statements", "CC0 1.0"],
  [
    "EPA ECHO",
    "Facility compliance and enforcement history",
    "US government data. Records before November 2000 have unknown quality.",
  ],
  [
    "US Department of Labor (OSHA)",
    "Workplace inspection and citation records",
    "US government data",
  ],
  ["NHTSA", "Vehicle and equipment recalls", "US government data"],
  ["CPSC", "Consumer product recalls", "US government API"],
  ["FDA (openFDA)", "Enforcement reports", "US government data"],
  [
    "GDELT",
    "News discovery: title, link, outlet, language, time",
    "Free for research use. Metadata only. Publishers keep copyright.",
  ],
];

export default async function MethodologyPage() {
  const stats = await getStats();
  const ev = stats?.evaluation;
  return (
    <>
      <PageHero
        eyebrow="Methodology"
        title="How matching and scoring work, and how they are measured"
        text="This page states what is built, what has been measured, and what has not."
      />

      <Section id="sources">
        <SectionHead eyebrow="Data" title="Sources and terms" />
        <div
          className="overflow-x-auto"
          tabIndex={0}
          role="region"
          aria-label="Table, scrolls horizontally on small screens"
        >
          <table className="w-full min-w-[640px] border-collapse text-left text-[15px]">
            <caption className="sr-only">Data sources, what they provide, and their terms</caption>
            <thead>
              <tr className="border-line border-b">
                <th scope="col" className="py-3 pr-4">
                  Source
                </th>
                <th scope="col" className="px-4 py-3">
                  Used for
                </th>
                <th scope="col" className="px-4 py-3">
                  Terms
                </th>
              </tr>
            </thead>
            <tbody>
              {SOURCES.map((s) => (
                <tr key={s[0]} className="border-line border-b align-top">
                  <th scope="row" className="text-ink py-3 pr-4 font-medium">
                    {s[0]}
                  </th>
                  <td className="px-4 py-3 text-slate-700">{s[1]}</td>
                  <td className="px-4 py-3 text-slate-700">{s[2]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-[15px] leading-7 text-slate-700">
          The project builds on the open-source BELA and BLINK releases and is not affiliated with
          their authors. Structured regulator and filing data is mostly from the United States. News
          coverage can be global. A quiet profile for a supplier outside the United States should
          not be read as a clean one.
        </p>
        {stats?.sources.length ? (
          <ul className="mt-4 grid gap-2 text-[15px] text-slate-700 sm:grid-cols-2">
            {stats.sources.map((s) => (
              <li key={s.source}>
                {SOURCE_LABELS[s.source] ?? s.source}: {fmt(s.records)} records loaded,{" "}
                {fmt(s.linked)} linked to a company in this environment
              </li>
            ))}
          </ul>
        ) : null}
      </Section>

      <Section tone="white">
        <SectionHead eyebrow="Models" title="What runs today" />
        <div className="grid gap-6 md:grid-cols-2">
          {[
            {
              t: "Structured resolution",
              p: "Name normalization, identifier matching, trigram retrieval, and a Fellegi-Sunter pair model with a logistic combiner and calibration. Routing thresholds are versioned, and their status is shown as provisional until they are fitted on gold labels.",
            },
            {
              t: "News linking",
              p: "Sentence extraction and a keyword topic filter, a mention linker with pluggable back ends, and a language model adjudication step. Article text is delimited and sanitized, and the model answers in a validated schema. If a model is unavailable the pipeline falls back and marks the result as reduced confidence.",
            },
            {
              t: "Event classification and scoring",
              p: "Rules map each regulator field to an event type and severity band. The risk score is 100 times one minus the product of one minus each capped event impact, where an impact is severity, recency decay, link confidence, relationship weight, and source reliability multiplied.",
            },
            {
              t: "Status of the linking models",
              p: "The BELA mention linker and the fine-tuned BLINK re-ranker are integrated through service interfaces. Their accuracy on company mentions has not been measured here, and the spikes that decide how they are deployed are still to be run.",
            },
          ].map((m) => (
            <Card key={m.t} className="p-6">
              <h3 className="text-h4">{m.t}</h3>
              <p className="mt-2 text-[15px] leading-7 text-slate-700">{m.p}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section>
        <SectionHead eyebrow="Evaluation" title="Training data and evaluation design" />
        <ul className="max-w-3xl list-disc space-y-3 pl-6 text-[17px] leading-8 text-slate-800">
          <li>
            Synthetic training pairs perturb canonical names and aliases (suffix changes,
            abbreviations, typing errors, token order, location and plant suffixes) and add hard
            negatives.
          </li>
          <li>
            Training and test data are split by company. Companies in the gold set are excluded from
            synthetic training data.
          </li>
          <li>
            The gold design is 400 structured records, at least 100 of them hard cases, and 200 news
            mentions, with double annotation on a portion. A gold set is not yet published.
          </li>
          <li>
            Systems compared on the same records: fuzzy matching, the probabilistic model alone, and
            the hybrid pipeline.
          </li>
          <li>
            Measures: precision of accepted matches, recall at k, false links per 1,000 records, NIL
            F1, review rate, and latency.
          </li>
        </ul>
      </Section>

      <Section tone="white" id="results">
        <SectionHead eyebrow="Results" title="Latest evaluation run" />
        {ev ? (
          <>
            <p className="mb-4 text-[15px] text-slate-700">
              Data: {ev.data ?? "not stated"}. Records: {ev.records ?? "n/a"}. Configuration status:{" "}
              {ev.config_status ?? "n/a"}.
            </p>
            <div
              className="overflow-x-auto"
              tabIndex={0}
              role="region"
              aria-label="Table, scrolls horizontally on small screens"
            >
              <table className="w-full min-w-[480px] border-collapse text-left text-[15px]">
                <caption className="sr-only">Evaluation results by system</caption>
                <thead>
                  <tr className="border-line border-b">
                    <th scope="col" className="py-3 pr-4">
                      System
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Precision of accepted matches
                    </th>
                    <th scope="col" className="px-4 py-3">
                      False links per 1,000
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ev.systems.map((s) => (
                    <tr key={s.system} className="border-line border-b">
                      <th scope="row" className="text-ink py-3 pr-4 font-medium">
                        {s.system}
                      </th>
                      <td className="px-4 py-3">
                        {s.precision != null ? `${(s.precision * 100).toFixed(1)}%` : "n/a"}
                      </td>
                      <td className="px-4 py-3">
                        {s.false_links_per_1000 != null ? s.false_links_per_1000.toFixed(1) : "n/a"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="max-w-3xl text-[17px] leading-8 text-slate-800">
            No evaluation run has been published in this environment. Results appear here, with the
            data they were computed on, after the evaluation is run. Synthetic results are always
            labeled as synthetic and are never presented as gold results.
          </p>
        )}
      </Section>

      <Section>
        <SectionHead eyebrow="Limits" title="Known limitations" />
        <ul className="max-w-3xl list-disc space-y-3 pl-6 text-[17px] leading-8 text-slate-800">
          <li>Structured regulator coverage is mostly the United States.</li>
          <li>
            Ownership data is strongest for large listed companies and can be out of date. Every
            edge shows its source and date.
          </li>
          <li>
            Matching is probabilistic. Wrong links are possible, and the product routes uncertain
            cases to review.
          </li>
          <li>Absence of a record is not evidence of good practice.</li>
          <li>Risk signals are leads for human review and not statements of fault.</li>
        </ul>
      </Section>

      <Section tone="white" id="corrections">
        <SectionHead eyebrow="Corrections" title="How to correct the record" />
        <p className="max-w-3xl text-[17px] leading-8 text-slate-700">
          A customer can flag a wrong link or an outdated record from the application. The request
          is stored, routed to the platform review queue, and answered. A company that believes a
          public record has been linked to it in error can write to the contact address on the
          company page with the record and the reason.
        </p>
      </Section>
    </>
  );
}
