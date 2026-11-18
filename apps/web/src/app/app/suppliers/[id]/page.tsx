"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { ChartCard } from "@/components/app/chart-card";
import { CorrectionDialog } from "@/components/app/correction-dialog";
import { DataTable } from "@/components/app/data-table";
import {
  ErrorState,
  PageHeader,
  Panel,
  RiskBadge,
  SeverityBadge,
  SkeletonRows,
} from "@/components/app/ui";
import { UsMapCard } from "@/components/app/us-map";
import { Badge } from "@/components/ui/badge";
import { Breadcrumbs } from "@/components/ui/breadcrumbs";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { dateShort, dateTime, label } from "@/lib/app/format";
import { useAction } from "@/lib/app/hooks";
import { can, useMe } from "@/lib/app/session";
import type { AlertRow, Page } from "@/lib/app/types";

interface Component_ {
  event_id: number;
  category: string;
  severity_weight: number;
  recency_decay: number;
  link_confidence: number;
  relation_weight: number;
  source_reliability: number;
  event_impact: number;
  title: string;
  source: string;
  url: string | null;
  reported_at: string;
}
interface ProfileEvent {
  id: number;
  source: string;
  event_type: string;
  severity: number;
  reported_at: string;
  title: string;
  summary: string | null;
  url: string | null;
  state: string | null;
  via: number;
  relation: string;
  path: number[];
}
interface Profile {
  supplier: {
    id: string;
    uploaded_name: string;
    tier: string | null;
    status: string;
    confidence: number | null;
    attributes: Record<string, string>;
    resolution_detail: Record<string, unknown>;
  };
  company: {
    id: number;
    canonical_name: string;
    cik: number | null;
    lei: string | null;
    wikidata_qid: string | null;
    tickers: string[];
    hq_city: string | null;
    hq_state: string | null;
    is_public: boolean;
    aliases: { alias: string; alias_type: string }[];
  } | null;
  family: {
    nodes: { id: number; name: string; hop: number; direction: string; in_portfolio: boolean }[];
    edges: {
      parent_id: number;
      child_id: number;
      rel_type: string;
      ownership_share: number | null;
      source: string;
      as_of: string | null;
    }[];
  } | null;
  facilities: {
    registry_id: string;
    name: string;
    city: string | null;
    state: string | null;
    latitude: number | null;
    longitude: number | null;
    source: string;
    link_confidence: number | null;
  }[];
  events: ProfileEvent[];
  sources: { source: string; name: string; method: string; score: number }[];
  risk: {
    score: number;
    level: string;
    config_version: string;
    computed_at: string;
    components: Component_[];
    category_scores: Record<string, number>;
  } | null;
  disclaimer: string;
}

export default function SupplierDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const me = useMe().data;
  const q = useQuery({
    queryKey: ["supplier", id],
    queryFn: () => api<Profile>(`/suppliers/${id}/profile`),
  });
  const alerts = useQuery({
    queryKey: ["alerts", "supplier", id],
    queryFn: () => api<Page<AlertRow>>(`/alerts?supplier_id=${id}&limit=50`),
  });
  const [corr, setCorr] = useState(false);
  const tier = useAction(
    (t: string) => api(`/suppliers/${id}`, { method: "PATCH", json: { tier: t } }),
    { success: "Tier updated", invalidate: [["supplier", id], ["suppliers"]] },
  );
  const report = useAction(() => api("/reports/supplier/" + id, { method: "POST" }), {
    success: "Report requested. Find it on the Reports page.",
  });

  if (q.isLoading) return <SkeletonRows rows={8} />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => void q.refetch()} />;
  const p = q.data;
  const s = p.supplier;
  const names = new Map<number, string>([
    ...(p.family?.nodes ?? []).map((n) => [n.id, n.name] as [number, string]),
    ...(p.company ? [[p.company.id, p.company.canonical_name] as [number, string]] : []),
  ]);

  const overview = (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title="Score breakdown">
        {p.risk ? (
          <>
            <p className="mb-3 text-sm text-slate-600">
              Score {p.risk.score.toFixed(1)} ({p.risk.level}) from configuration{" "}
              {p.risk.config_version}, computed {dateTime(p.risk.computed_at)}. Each impact
              multiplies severity, recency, link confidence, relationship weight, and source
              reliability.
            </p>
            <DataTable<Component_>
              id="components"
              caption="Score components"
              data={p.risk.components}
              rowKey={(r) => String(r.event_id)}
              exportName="score-components"
              columns={[
                {
                  header: "Event",
                  accessorKey: "title",
                  cell: (c) => (
                    <Link
                      className="text-link underline underline-offset-2"
                      href={`/app/events/${c.row.original.event_id}`}
                    >
                      {c.row.original.title}
                    </Link>
                  ),
                },
                { header: "Category", accessorFn: (r) => label(r.category) },
                { header: "Severity", accessorKey: "severity_weight" },
                { header: "Recency", accessorFn: (r) => +r.recency_decay.toFixed(2) },
                { header: "Link", accessorFn: (r) => +r.link_confidence.toFixed(2) },
                { header: "Relation", accessorKey: "relation_weight" },
                { header: "Reliability", accessorKey: "source_reliability" },
                { header: "Impact", accessorFn: (r) => +r.event_impact.toFixed(3) },
              ]}
            />
          </>
        ) : (
          <p className="text-sm text-slate-600">
            This supplier has not been scored. Scores need a resolved company and at least one
            linked event.
          </p>
        )}
      </Panel>
      <ChartCard
        title="Category sub-scores"
        subtitle="Score by event category"
        empty={!p.risk || !Object.keys(p.risk.category_scores).length}
        filename="category-scores"
        table={{
          columns: ["Category", "Score"],
          rows: Object.entries(p.risk?.category_scores ?? {}).map(([k, v]) => ({
            Category: label(k),
            Score: v,
          })),
        }}
        option={{
          grid: { left: 150, right: 24, top: 8, bottom: 40 },
          tooltip: {},
          xAxis: {
            type: "value",
            max: 100,
            name: "Score (0 to 100)",
            nameLocation: "middle",
            nameGap: 28,
            splitLine: { lineStyle: { color: "#94a3b833" } },
          },
          yAxis: { type: "category", data: Object.keys(p.risk?.category_scores ?? {}).map(label) },
          series: [
            {
              type: "bar",
              data: Object.values(p.risk?.category_scores ?? {}),
              label: { show: true, position: "right" },
            },
          ],
        }}
      />
    </div>
  );

  const eventsTab = (
    <Panel title="Events that reach this supplier">
      {p.events.length === 0 ? (
        <p className="text-sm text-slate-600">No linked events yet.</p>
      ) : (
        <ol className="border-line space-y-4 border-l pl-5">
          {p.events.map((e) => (
            <li key={e.id} className="relative">
              <span
                className="bg-chart-1 absolute top-1.5 -left-[26px] size-2.5 rounded-full"
                aria-hidden
              />
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="brand">{e.source}</Badge>
                <SeverityBadge severity={e.severity} />
                <span className="text-sm text-slate-600">{dateShort(e.reported_at)}</span>
                <Badge tone="neutral">
                  {e.relation === "direct" ? "Direct" : `Through ${e.relation}`}
                </Badge>
              </div>
              <Link
                href={`/app/events/${e.id}`}
                className="text-link mt-1 block font-medium underline underline-offset-2"
              >
                {e.title}
              </Link>
              {e.summary && <p className="text-sm text-slate-600">{e.summary}</p>}
              {e.path.length > 1 && (
                <p className="text-xs text-slate-600">
                  Path: {e.path.map((c) => names.get(c) ?? c).join(" to ")}
                </p>
              )}
              {e.url && (
                <a
                  href={e.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-link text-xs underline underline-offset-2"
                >
                  Source record (opens in a new tab)
                </a>
              )}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );

  const edges = p.family?.edges ?? [];
  const familyTab = (
    <Panel title="Corporate family">
      {!p.family || edges.length === 0 ? (
        <p className="text-sm text-slate-600">
          No parent or subsidiary relationships are recorded for this company.
        </p>
      ) : (
        <ul className="space-y-2">
          {edges.map((e, i) => (
            <li key={i} className="border-line rounded-[10px] border p-3 text-sm">
              <span className="text-ink font-medium">{names.get(e.parent_id) ?? e.parent_id}</span>{" "}
              owns{" "}
              <span className="text-ink font-medium">{names.get(e.child_id) ?? e.child_id}</span>
              <span className="block text-slate-600">
                {label(e.rel_type)}
                {e.ownership_share != null ? `, ${(e.ownership_share * 100).toFixed(0)}%` : ""}.
                Source {e.source}, as of {dateShort(e.as_of)}.
              </span>
              {p.family?.nodes.find((n) => n.id === e.parent_id || n.id === e.child_id)
                ?.in_portfolio && <Badge tone="brand">In your portfolio</Badge>}
            </li>
          ))}
        </ul>
      )}
      {p.company && (
        <p className="mt-3 text-sm">
          <Link
            className="text-link underline underline-offset-2"
            href={`/app/explorer?company=${p.company.id}`}
          >
            Open in the explorer
          </Link>
        </p>
      )}
    </Panel>
  );

  const facilitiesTab = (
    <div className="space-y-6">
      <UsMapCard
        title="Facilities"
        subtitle="Facility locations"
        states={[]}
        points={p.facilities
          .filter((f) => f.latitude != null && f.longitude != null)
          .map((f) => ({
            name: f.name,
            lat: f.latitude as number,
            lon: f.longitude as number,
            value: 1,
          }))}
      />
      <Panel title="Facility table">
        <DataTable<Profile["facilities"][number]>
          id="facilities"
          caption="Facilities"
          data={p.facilities}
          rowKey={(r) => r.registry_id}
          exportName="facilities"
          empty="No facilities are linked."
          columns={[
            { header: "Facility", accessorKey: "name" },
            { header: "City", accessorFn: (r) => r.city ?? "" },
            { header: "State", accessorFn: (r) => r.state ?? "" },
            { header: "Source", accessorKey: "source" },
            { header: "Link confidence", accessorFn: (r) => r.link_confidence ?? 0 },
          ]}
        />
      </Panel>
    </div>
  );

  const sourcesTab = (
    <Panel title="Source records">
      <DataTable<Profile["sources"][number]>
        id="sources"
        caption="Source records linked to this company"
        data={p.sources}
        rowKey={(r) => r.source + r.name}
        exportName="source-records"
        empty="No source records are linked to this company yet."
        columns={[
          { header: "Source", accessorKey: "source" },
          { header: "Name in the source", accessorKey: "name" },
          { header: "Link method", accessorKey: "method" },
          { header: "Score", accessorKey: "score" },
        ]}
      />
    </Panel>
  );

  const activityTab = (
    <Panel title="Alerts for this supplier">
      {alerts.data?.items.length ? (
        <ul className="divide-line divide-y">
          {alerts.data.items.map((a) => (
            <li key={a.id} className="flex justify-between gap-3 py-2.5 text-sm">
              <span>
                {a.detail ?? label(a.kind)}
                <span className="block text-xs text-slate-600">{dateTime(a.created_at)}</span>
              </span>
              <Badge tone={a.status === "new" ? "warning" : "neutral"}>{label(a.status)}</Badge>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-600">
          No alerts for this supplier. Open the{" "}
          <Link href="/app/alerts" className="text-link underline underline-offset-2">
            alert queue
          </Link>{" "}
          to work alerts and add comments.
        </p>
      )}
    </Panel>
  );

  return (
    <>
      <Breadcrumbs
        items={[{ title: "Suppliers", href: "/app/suppliers" }, { title: s.uploaded_name }]}
      />
      <div className="mt-3" />
      <PageHeader
        title={p.company?.canonical_name ?? s.uploaded_name}
        text={`Uploaded as "${s.uploaded_name}". Status ${label(s.status)}${s.confidence != null ? `, confidence ${(s.confidence * 100).toFixed(0)}%` : ""}, method ${String(s.resolution_detail.method ?? "n/a")}.`}
        actions={
          <>
            {p.risk ? (
              <RiskBadge level={p.risk.level} score={p.risk.score} />
            ) : (
              <RiskBadge level={null} />
            )}
            {can(me, "upload_review") && (
              <>
                <label htmlFor="tier" className="sr-only">
                  Change tier
                </label>
                <Select
                  id="tier"
                  className="h-9 w-32"
                  value={s.tier ?? ""}
                  onChange={(e) => tier.mutate(e.target.value)}
                >
                  <option value="" disabled>
                    Tier
                  </option>
                  {["tier_1", "tier_2", "tier_3"].map((t) => (
                    <option key={t} value={t}>
                      {label(t)}
                    </option>
                  ))}
                </Select>
              </>
            )}
            {can(me, "manage_rules") && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => report.mutate(undefined)}
                disabled={report.isPending}
              >
                Export report
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={() => setCorr(true)}>
              Request correction
            </Button>
          </>
        }
      />
      {p.company && (
        <dl className="mb-6 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          {[
            ["CIK", p.company.cik],
            ["LEI", p.company.lei],
            ["Wikidata", p.company.wikidata_qid],
            ["Tickers", p.company.tickers.join(", ")],
            ["Headquarters", [p.company.hq_city, p.company.hq_state].filter(Boolean).join(", ")],
            ["Aliases", p.company.aliases.length],
          ].map(([k, v]) => (
            <div key={String(k)}>
              <dt className="text-xs text-slate-600">{k}</dt>
              <dd className="text-ink font-mono">
                {v === null || v === "" || v === undefined ? "n/a" : String(v)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <Tabs
        label="Supplier sections"
        items={[
          { id: "overview", label: "Overview", content: overview },
          { id: "events", label: "Events", content: eventsTab },
          { id: "family", label: "Family", content: familyTab },
          { id: "facilities", label: "Facilities", content: facilitiesTab },
          { id: "sources", label: "Sources", content: sourcesTab },
          { id: "activity", label: "Activity", content: activityTab },
        ]}
      />
      <p className="mt-6 text-xs text-slate-600">{p.disclaimer}</p>
      <CorrectionDialog
        open={corr}
        onOpenChange={setCorr}
        supplierId={id}
        companyId={p.company?.id}
      />
    </>
  );
}
