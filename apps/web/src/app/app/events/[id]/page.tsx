"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { CorrectionDialog } from "@/components/app/correction-dialog";
import { ErrorState, PageHeader, Panel, SeverityBadge, SkeletonRows } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Breadcrumbs } from "@/components/ui/breadcrumbs";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { dateTime, label } from "@/lib/app/format";

interface Cand {
  rank: number;
  company_id: number;
  canonical_name: string;
  bela_score: number | null;
  blink_score: number | null;
  splink_score: number | null;
  llm_label: string | null;
}
interface Ent {
  id: number;
  company_id: number;
  canonical_name: string;
  role: string;
  method: string;
  score: number;
  candidates: Cand[];
}
interface Detail {
  id: number;
  source: string;
  event_type: string;
  severity: number;
  reported_at: string;
  occurred_at: string | null;
  title: string;
  summary: string | null;
  url: string | null;
  state: string | null;
  city: string | null;
  rules_version: string | null;
  entities: Ent[];
  evidence: {
    kind: "news" | "record";
    text: string;
    spans: { start: number; end: number; company_id: number }[];
    fields: Record<string, unknown>;
  };
  reaches_suppliers: {
    supplier_id: string;
    supplier_name: string;
    relation: string;
    path: string[];
  }[];
  disclaimer: string;
}

function Highlighted({ text, spans }: { text: string; spans: { start: number; end: number }[] }) {
  const out: React.ReactNode[] = [];
  let at = 0;
  spans.forEach((s, i) => {
    out.push(text.slice(at, s.start));
    out.push(
      <mark key={i} className="rounded bg-[#fff1c2] px-0.5 text-[#3d2e00]">
        {text.slice(s.start, s.end)}
      </mark>,
    );
    at = s.end;
  });
  out.push(text.slice(at));
  return <p className="text-ink text-[16px] leading-7">{out}</p>;
}

const n = (v: number | null) => (v == null ? "n/a" : v.toFixed(2));

export default function EventDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const q = useQuery({ queryKey: ["event", id], queryFn: () => api<Detail>(`/events/${id}`) });
  const [corr, setCorr] = useState(false);
  if (q.isLoading) return <SkeletonRows rows={8} />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => void q.refetch()} />;
  const e = q.data;
  return (
    <>
      <Breadcrumbs items={[{ title: "Events", href: "/app/events" }, { title: `Event ${e.id}` }]} />
      <div className="mt-3" />
      <PageHeader
        title={e.title}
        text={`${label(e.event_type)} reported ${dateTime(e.reported_at)}${e.state ? ` in ${e.city ? e.city + ", " : ""}${e.state}` : ""}.`}
        actions={
          <>
            <Badge tone="brand">{e.source}</Badge>
            <SeverityBadge severity={e.severity} />
            <Button variant="secondary" size="sm" onClick={() => setCorr(true)}>
              Request correction
            </Button>
          </>
        }
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title={
            e.evidence.kind === "news" ? "Evidence: article sentence" : "Evidence: source record"
          }
        >
          {e.evidence.kind === "news" ? (
            <Highlighted text={e.evidence.text} spans={e.evidence.spans} />
          ) : (
            <>
              <p className="text-ink mb-3 text-[15px] leading-7">{e.evidence.text}</p>
              <dl className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(e.evidence.fields).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs text-slate-600">{label(k)}</dt>
                    <dd className="text-ink font-mono">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}
          {e.url && (
            <p className="mt-4 text-sm">
              <a
                href={e.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-link underline underline-offset-2"
              >
                Open the source record (new tab)
              </a>
            </p>
          )}
          <p className="mt-2 text-xs text-slate-600">
            Only a short snippet is stored. Publishers keep the copyright in news content.
          </p>
        </Panel>
        <Panel title="Reaches your suppliers">
          {e.reaches_suppliers.length === 0 ? (
            <p className="text-sm text-slate-600">
              This event does not reach a supplier in your portfolio.
            </p>
          ) : (
            <ul className="space-y-3">
              {e.reaches_suppliers.map((r) => (
                <li key={r.supplier_id} className="border-line rounded-[10px] border p-3 text-sm">
                  <Link
                    href={`/app/suppliers/${r.supplier_id}`}
                    className="text-link font-medium underline underline-offset-2"
                  >
                    {r.supplier_name}
                  </Link>
                  <Badge tone="neutral" className="ml-2">
                    {r.relation === "direct"
                      ? "Direct link"
                      : r.relation === "parent"
                        ? "Event at a parent"
                        : "Event at a subsidiary"}
                  </Badge>
                  <p className="mt-1 text-xs text-slate-600">Path: {r.path.join(" to ")}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <Panel title="Resolution transparency" className="mt-6">
        <p className="mb-3 text-sm text-slate-600">
          How the platform decided which company this event concerns. Scores are shown as stored;
          blank means that model did not run for this record.
        </p>
        {e.entities.map((en) => (
          <div key={en.id} className="mb-5">
            <p className="text-ink text-sm">
              Final decision: <strong>{en.canonical_name}</strong> ({en.role}) by method {en.method}
              , confidence {(en.score * 100).toFixed(0)}%.
            </p>
            <div
              className="mt-2 overflow-x-auto"
              tabIndex={0}
              role="region"
              aria-label="Candidates considered"
            >
              <table className="w-full min-w-[560px] text-left text-sm">
                <caption className="sr-only">Candidates considered for {en.canonical_name}</caption>
                <thead>
                  <tr className="border-line border-b">
                    {["Rank", "Candidate", "BELA", "BLINK", "Splink weight", "Language model"].map(
                      (h) => (
                        <th key={h} scope="col" className="text-ink px-2 py-1.5 font-medium">
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {en.candidates.map((c) => (
                    <tr key={c.rank} className="border-line border-b">
                      <td className="px-2 py-1.5">{c.rank}</td>
                      <td className="px-2 py-1.5">
                        {c.canonical_name}
                        {c.company_id === en.company_id && (
                          <Badge tone="success" className="ml-2">
                            Chosen
                          </Badge>
                        )}
                      </td>
                      <td className="px-2 py-1.5 font-mono">{n(c.bela_score)}</td>
                      <td className="px-2 py-1.5 font-mono">{n(c.blink_score)}</td>
                      <td className="px-2 py-1.5 font-mono">{n(c.splink_score)}</td>
                      <td className="px-2 py-1.5">{c.llm_label ?? "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </Panel>
      <p className="mt-6 text-xs text-slate-600">{e.disclaimer}</p>
      <CorrectionDialog
        open={corr}
        onOpenChange={setCorr}
        eventId={e.id}
        companyId={e.entities[0]?.company_id}
      />
    </>
  );
}
