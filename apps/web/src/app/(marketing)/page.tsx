import { ArrowRight, Lock, ScrollText, ShieldCheck, Users } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { FamilyGraphic, NamesArt, SheetArt, SubsidiaryArt } from "@/components/art/illustrations";
import { Icon } from "@/components/art/icon";
import { EventsArt, MonitorArt, ResolveArt, UploadArt } from "@/components/art/illustrations";
import { Eyebrow, JsonLd, Section, SectionHead } from "@/components/marketing/blocks";
import { ProductMock } from "@/components/marketing/product-mock";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, HoverCard } from "@/components/ui/card";
import { Stepper } from "@/components/ui/stepper";
import { Tabs } from "@/components/ui/tabs";
import { ARTICLES } from "@/lib/articles";
import { INDUSTRIES } from "@/content/industries";
import { SITE, type IconName } from "@/lib/site";
import { fmt, getStats, SOURCE_LABELS } from "@/lib/stats";

export const revalidate = 3600;
export const metadata: Metadata = {
  title: { absolute: `${SITE.name}: ${SITE.tagline}` },
  description: "See every risk behind every supplier, under every name.",
};

const CAPABILITIES: { title: string; text: string; icon: IconName }[] = [
  {
    title: "Entity resolution",
    text: "Blocking, retrieval, probabilistic scoring, and re-ranking match messy names to canonical companies. Every candidate and score is stored.",
    icon: "search",
  },
  {
    title: "Corporate family mapping",
    text: "Ownership edges from GLEIF, SEC Exhibit 21 filings, and Wikidata carry a source and an as-of date.",
    icon: "network",
  },
  {
    title: "Regulator and recall events",
    text: "EPA, OSHA, NHTSA, CPSC, and FDA records are normalized to one event schema with the original record linked.",
    icon: "alert",
  },
  {
    title: "News event detection",
    text: "Company mentions in article text are linked and classified. Articles are treated as untrusted input.",
    icon: "radar",
  },
  {
    title: "Review workflow and audit trail",
    text: "Uncertain matches go to a reviewer with the evidence side by side. Decisions land in a tamper-evident log.",
    icon: "users",
  },
  {
    title: "API and batch upload",
    text: "Upload a CSV or call the API with a scoped key. Results export with canonical identifiers.",
    icon: "code",
  },
];

export default async function HomePage() {
  const stats = await getStats();
  const linked =
    stats?.sources.filter((s) => s.source !== "news").reduce((n, s) => n + s.linked, 0) ?? 0;
  const hybrid = stats?.evaluation?.systems.find((s) => s.system.toLowerCase().includes("hybrid"));
  const fuzzy = stats?.evaluation?.systems.find(
    (s) => s.system.toLowerCase().includes("fuzzy") || s.system.toLowerCase().includes("rapidfuzz"),
  );
  const reduction =
    hybrid?.false_links_per_1000 != null &&
    fuzzy?.false_links_per_1000 != null &&
    fuzzy.false_links_per_1000 > 0
      ? Math.round((1 - hybrid.false_links_per_1000 / fuzzy.false_links_per_1000) * 100)
      : null;
  const evalLabel = stats?.evaluation?.data ?? null;

  const proof: { value: string; label: string }[] = [];
  if (stats && stats.companies > 0)
    proof.push({ value: fmt(stats.companies), label: "canonical companies indexed" });
  if (linked > 0)
    proof.push({ value: fmt(linked), label: "regulator records linked to a company" });
  if (hybrid?.precision != null)
    proof.push({
      value: `${(hybrid.precision * 100).toFixed(1)}%`,
      label: "precision of automatic matches",
    });
  if (reduction != null)
    proof.push({ value: `${reduction}%`, label: "fewer false links than fuzzy matching" });

  const steps = [
    {
      title: "Upload your supplier list",
      text: "Drop in a CSV from your ERP. Map columns once and keep your own identifiers.",
      visual: <UploadArt />,
    },
    {
      title: "Resolve to canonical companies",
      text: "Each row is matched to one company, sent to review, or left unresolved. Nothing is attached silently.",
      visual: <ResolveArt />,
    },
    {
      title: "Attach events from news and regulators",
      text: "Public records and news events are linked to the same companies, with the source and date shown.",
      visual: <EventsArt />,
    },
    {
      title: "Monitor risk across the corporate family",
      text: "A record at a subsidiary reaches the parent supplier, weighted by the relationship.",
      visual: <MonitorArt />,
    },
  ];

  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Organization",
          name: SITE.name,
          url: SITE.url,
          description: SITE.tagline,
        }}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebSite",
          name: SITE.name,
          url: SITE.url,
        }}
      />

      <section className="bg-page overflow-hidden pt-12 pb-16 lg:pt-20 lg:pb-24">
        <div className="container-page grid items-center gap-12 lg:grid-cols-[1.05fr_1fr] [&>*]:min-w-0">
          <div>
            <Eyebrow>Supplier and counterparty risk intelligence</Eyebrow>
            <h1 className="text-display max-w-xl">
              See every risk behind every supplier, under every name.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-700">
              Entity resolution connects news, regulator records, and corporate filings to the
              companies in your supply base, including their parents and subsidiaries.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/contact">Request a demo</Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <Link href="/login">Log in to the platform</Link>
              </Button>
            </div>
          </div>
          <div className="relative min-h-[320px] lg:min-h-[400px]">
            <div
              aria-hidden
              className="absolute -inset-6 rounded-[32px] bg-[radial-gradient(60%_60%_at_30%_20%,#cfe0f7_0%,transparent_70%),radial-gradient(50%_50%_at_80%_80%,#cdeeee_0%,transparent_70%)]"
            />
            <div className="relative">
              <ProductMock />
              <Card className="absolute -bottom-6 -left-2 hidden w-56 p-4 shadow-[var(--shadow-2)] sm:block">
                <p className="text-xs text-slate-600">Supplier risk</p>
                <p className="mt-1 flex items-baseline gap-2">
                  <span className="text-ink text-2xl font-semibold">61</span>
                  <Badge tone="high">High</Badge>
                </p>
                <p className="mt-1 text-xs text-slate-600">Demo data</p>
              </Card>
              <Card className="absolute -top-5 -right-2 hidden w-60 p-3 shadow-[var(--shadow-2)] md:block">
                <FamilyGraphic />
              </Card>
            </div>
          </div>
        </div>
      </section>

      <Section tone="white" className="!py-10 lg:!py-14">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {proof.map((p) => (
            <div key={p.label}>
              <p className="text-ink text-4xl font-semibold tracking-tight">{p.value}</p>
              <p className="mt-1 text-[15px] text-slate-700">{p.label}</p>
            </div>
          ))}
          {proof.length < 4 && (
            <div className="sm:col-span-2">
              <p className="text-[15px] leading-7 text-slate-700">
                Evaluation figures appear here only when they are measured. Precision on the gold
                set and the reduction in false links versus fuzzy matching are reported on the
                methodology page, with the data they were computed on.
              </p>
            </div>
          )}
        </div>
        <p className="mt-6 text-sm text-slate-600">
          Figures are read from the database and the latest evaluation run
          {evalLabel ? ` (${evalLabel})` : ""}. See{" "}
          <Link href="/methodology" className="text-brand-600 underline underline-offset-2">
            methodology
          </Link>
          .
        </p>
      </Section>

      <Section>
        <SectionHead eyebrow="The problem" title="Why a name match is not enough" />
        <div className="grid gap-6 md:grid-cols-3">
          {[
            {
              t: "One company, many names",
              p: "The same supplier appears as an uppercase string in one system and a trading name in another. Exact matching misses it and loose matching joins the wrong companies.",
              a: <NamesArt />,
            },
            {
              t: "Risk hides in subsidiaries",
              p: "A record often names a plant or a subsidiary, not the company you pay. Without the corporate family, the signal never reaches your supplier.",
              a: <SubsidiaryArt />,
            },
            {
              t: "Spreadsheets do not scale",
              p: "Reviewing thousands of rows by hand is slow and inconsistent. A queue with evidence and an audit trail keeps the work reviewable.",
              a: <SheetArt />,
            },
          ].map((c) => (
            <HoverCard key={c.t} className="p-6">
              <div className="mb-5 rounded-[10px] bg-slate-50 p-3">{c.a}</div>
              <h3 className="text-h4">{c.t}</h3>
              <p className="mt-2 text-[15px] leading-7 text-slate-700">{c.p}</p>
            </HoverCard>
          ))}
        </div>
      </Section>

      <Section tone="white">
        <SectionHead
          eyebrow="How it works"
          title="From a supplier list to monitored risk in four steps"
        />
        <Stepper steps={steps} />
      </Section>

      <Section>
        <SectionHead eyebrow="Capabilities" title="What the platform does" />
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map((c) => (
            <HoverCard key={c.title} className="p-6">
              <span className="bg-brand-100 text-brand-600 mb-4 flex size-11 items-center justify-center rounded-[10px]">
                <Icon name={c.icon} className="size-6" />
              </span>
              <h3 className="text-h4">{c.title}</h3>
              <p className="mt-2 text-[15px] leading-7 text-slate-700">{c.text}</p>
            </HoverCard>
          ))}
        </div>
      </Section>

      <Section tone="white">
        <SectionHead
          eyebrow="Product"
          title="Built for the reviewer, the analyst, and the manager"
        />
        <Tabs
          label="Product views"
          items={[
            {
              id: "review",
              label: "Resolution review",
              content: (
                <Showcase caption="Each uploaded row is shown beside its candidates with scores and field agreement. Reviewers accept, choose another company, or mark the row as not in the database.">
                  <ProductMock />
                </Showcase>
              ),
            },
            {
              id: "profile",
              label: "Supplier risk profile",
              content: (
                <Showcase caption="The score is the combination of event impacts. Every component lists its event, source, date, and weights.">
                  <ProductMock variant="profile" />
                </Showcase>
              ),
            },
            {
              id: "family",
              label: "Corporate family graph",
              content: (
                <Showcase caption="Ownership edges carry their source and as-of date, so a roll-up can be checked against the filing.">
                  <ProductMock variant="family" />
                </Showcase>
              ),
            },
            {
              id: "analytics",
              label: "Portfolio analytics",
              content: (
                <Showcase caption="Trends, concentration by parent, and resolution quality for the whole supplier list.">
                  <ProductMock variant="analytics" />
                </Showcase>
              ),
            },
          ]}
        />
      </Section>

      <Section>
        <SectionHead eyebrow="Industries" title="Public records differ by sector" />
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {INDUSTRIES.map((i) => (
            <Link key={i.slug} href={`/industries/${i.slug}`} className="group">
              <HoverCard className="flex h-full flex-col overflow-hidden">
                <div
                  className="flex h-32 items-center justify-center"
                  style={{ background: `linear-gradient(135deg, ${i.tint[0]}, ${i.tint[1]})` }}
                >
                  <Icon name={i.icon} className="size-12 text-white" />
                </div>
                <div className="flex flex-1 flex-col p-5">
                  <h3 className="text-h4">{i.name}</h3>
                  <p className="mt-1 flex-1 text-[15px] leading-7 text-slate-700">{i.card}</p>
                  <span className="text-brand-600 mt-3 inline-flex items-center gap-1 text-sm font-medium">
                    Read more{" "}
                    <ArrowRight
                      className="size-4 transition-transform group-hover:translate-x-0.5"
                      aria-hidden
                    />
                  </span>
                </div>
              </HoverCard>
            </Link>
          ))}
        </div>
      </Section>

      <Section tone="white">
        <SectionHead
          eyebrow="Data coverage"
          title="Public sources, with their limits stated"
          text="Structured regulator and filing data is mostly from United States sources. News coverage can be global. Coverage outside the United States is narrower and is described on the methodology page."
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {["SEC filings", "GLEIF", "EPA", "OSHA", "NHTSA", "CPSC", "FDA", "Global news"].map(
            (s) => {
              const key = {
                EPA: "epa_echo",
                OSHA: "osha",
                NHTSA: "nhtsa",
                CPSC: "cpsc",
                FDA: "openfda",
                "Global news": "news",
              }[s];
              const row = key ? stats?.sources.find((r) => r.source === key) : undefined;
              return (
                <Card key={s} className="p-4">
                  <p className="text-ink font-medium">{s}</p>
                  <p className="mt-1 text-sm text-slate-600">
                    {row
                      ? `${fmt(row.records)} records loaded`
                      : key
                        ? "No records loaded in this environment"
                        : "Used for the company and ownership base"}
                  </p>
                </Card>
              );
            },
          )}
        </div>
        <p className="mt-4 text-sm text-slate-600">
          {stats
            ? `Counts come from this environment's database${stats.sources.length ? "" : ", which has no events loaded yet"}.`
            : "Counts are shown when the API is reachable."}{" "}
          Licenses and attributions are listed in the{" "}
          <Link href="/methodology#sources" className="text-brand-600 underline underline-offset-2">
            methodology
          </Link>
          .
        </p>
        {stats?.sources.length ? (
          <p className="sr-only">
            {stats.sources.map((s) => SOURCE_LABELS[s.source] ?? s.source).join(", ")}
          </p>
        ) : null}
      </Section>

      <Section tone="ink">
        <SectionHead
          dark
          eyebrow="Security"
          title="Designed for sensitive supplier data"
          text="The design follows common security practice. It does not claim any certification."
        />
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              i: Lock,
              t: "Encryption in transit and at rest",
              p: "TLS for all traffic. Sensitive identifiers are encrypted in the database.",
            },
            {
              i: ShieldCheck,
              t: "Role-based access with multi-factor sign-in",
              p: "Six roles. Multi-factor sign-in is mandatory for administrators.",
            },
            {
              i: Users,
              t: "Tenant isolation",
              p: "Row level security in the database separates one customer's data from another's.",
            },
            {
              i: ScrollText,
              t: "Tamper-evident audit log",
              p: "Each entry is chained to the previous one, so edits are detectable.",
            },
          ].map((x) => (
            <div key={x.t}>
              <x.i className="text-teal mb-3 size-7" aria-hidden />
              <h3 className="text-lg font-semibold text-white">{x.t}</h3>
              <p className="mt-1.5 text-[15px] leading-7 text-slate-300">{x.p}</p>
            </div>
          ))}
        </div>
        <Link
          href="/security"
          className="mt-8 inline-flex items-center gap-1 text-[15px] font-medium text-white underline underline-offset-4"
        >
          Read the security overview <ArrowRight className="size-4" aria-hidden />
        </Link>
      </Section>

      <Section>
        <SectionHead eyebrow="Insights" title="Latest articles" />
        <div className="grid gap-6 md:grid-cols-3">
          {ARTICLES.slice(0, 3).map((a) => (
            <Link key={a.slug} href={`/resources/${a.slug}`} className="group">
              <HoverCard className="flex h-full flex-col p-6">
                <p className="text-brand-600 text-xs font-medium tracking-wider uppercase">
                  {a.tag}
                </p>
                <h3 className="text-h4 group-hover:text-brand-600 mt-2">{a.title}</h3>
                <p className="mt-2 flex-1 text-[15px] leading-7 text-slate-700">{a.summary}</p>
                <p className="mt-4 text-sm text-slate-600">{a.readMinutes} min read</p>
              </HoverCard>
            </Link>
          ))}
        </div>
      </Section>

      <section className="bg-navy py-16 text-white">
        <div className="container-page">
          <div className="content-width grid items-center gap-8 lg:grid-cols-2">
            <div>
              <h2 className="text-h2 text-white">See it on a supplier list like yours</h2>
              <p className="mt-3 text-slate-300">
                Request a demonstration. We will walk through resolution, review, and monitoring
                with demo data.
              </p>
            </div>
            <form action="/contact" method="get" className="flex flex-col gap-3 sm:flex-row">
              <label htmlFor="cta-email" className="sr-only">
                Work email
              </label>
              <input
                id="cta-email"
                name="email"
                type="email"
                required
                autoComplete="email"
                placeholder="Work email"
                className="h-12 flex-1 rounded-[8px] border border-slate-500 bg-white/10 px-4 text-white placeholder:text-slate-300"
              />
              <Button type="submit" size="lg" className="text-ink bg-white hover:bg-slate-100">
                Request a demo
              </Button>
            </form>
          </div>
        </div>
      </section>
    </>
  );
}

function Showcase({ caption, children }: { caption: string; children: React.ReactNode }) {
  return (
    <div className="grid items-center gap-8 lg:grid-cols-[1.3fr_1fr] [&>*]:min-w-0">
      <div>{children}</div>
      <p className="text-[17px] leading-8 text-slate-700">{caption}</p>
    </div>
  );
}
