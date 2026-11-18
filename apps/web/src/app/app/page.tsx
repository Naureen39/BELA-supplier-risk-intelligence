"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ChartCard } from "@/components/app/chart-card";
import { DataTable } from "@/components/app/data-table";
import { UsMapCard } from "@/components/app/us-map";
import {
  ErrorState,
  KpiCard,
  PageHeader,
  Panel,
  RiskBadge,
  SkeletonRows,
} from "@/components/app/ui";
import { api } from "@/lib/api";
import { ago, dateShort, label, num, pct } from "@/lib/app/format";
import { flat, useCursorList } from "@/lib/app/hooks";
import { can, useMe } from "@/lib/app/session";
import type { AlertRow, EventRow, Page, Portfolio, ReviewRow, Supplier } from "@/lib/app/types";

export default function Overview() {
  const me = useMe().data;
  const mgr = can(me, "manage_rules");
  const [now] = useState(() => Date.now());
  const sup = useCursorList<Supplier>(["overview", "suppliers"], "/suppliers?limit=200");
  const alerts = useQuery({
    queryKey: ["alerts", "overview"],
    queryFn: () => api<Page<AlertRow>>("/alerts?limit=50"),
  });
  const events = useQuery({
    queryKey: ["overview", "events"],
    queryFn: () =>
      api<Page<EventRow>>(`/events?limit=100&since=${new Date(now - 30 * 86400000).toISOString()}`),
  });
  const reviews = useQuery({
    queryKey: ["overview", "reviews"],
    enabled: can(me, "upload_review"),
    queryFn: () => api<Page<ReviewRow>>("/reviews?limit=100"),
  });
  const port = useQuery({
    queryKey: ["overview", "portfolio"],
    enabled: mgr,
    queryFn: () => api<Portfolio>("/analytics/portfolio?granularity=week"),
  });

  const suppliers = useMemo(() => flat(sup.data), [sup.data]);
  const resolved = suppliers.filter(
    (s) => s.status === "auto_resolved" || s.status === "resolved",
  ).length;
  const hi = suppliers.filter((s) => s.risk_level === "high" || s.risk_level === "critical").length;
  const week = (events.data?.items ?? []).filter(
    (e) => now - new Date(e.reported_at).getTime() < 7 * 86400000,
  ).length;
  const open = (alerts.data?.items ?? []).filter(
    (a) => a.status === "new" || a.status === "in_review",
  ).length;
  const top = [...suppliers]
    .filter((s) => s.risk_score != null)
    .sort((a, b) => Number(b.risk_score) - Number(a.risk_score))
    .slice(0, 6);
  const byType = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of events.data?.items ?? []) m.set(e.event_type, (m.get(e.event_type) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [events.data]);
  const more = sup.hasNextPage;

  const trend = port.data?.risk_index_trend;
  return (
    <>
      <PageHeader
        title="Overview"
        text="Your monitored suppliers, new events, and open alerts."
        demo={port.data?.demo_data}
      />
      <section
        aria-label="Key figures"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6"
      >
        <KpiCard
          label="Monitored suppliers"
          value={sup.isLoading ? "..." : `${num(suppliers.length)}${more ? "+" : ""}`}
        />
        <KpiCard label="High or critical" value={sup.isLoading ? "..." : num(hi)} better="down" />
        <KpiCard
          label="Events in 7 days"
          value={events.isLoading ? "..." : num(week)}
          better="down"
        />
        <KpiCard label="Open alerts" value={alerts.isLoading ? "..." : num(open)} better="down" />
        <KpiCard
          label="Resolution rate"
          value={suppliers.length ? pct((100 * resolved) / suppliers.length, 0) : "n/a"}
        />
        <KpiCard
          label="Pending reviews"
          value={
            can(me, "upload_review")
              ? reviews.isLoading
                ? "..."
                : num(reviews.data?.items.length)
              : "n/a"
          }
          note={can(me, "upload_review") ? "" : "Analyst role needed"}
          better="down"
        />
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {mgr ? (
          <ChartCard
            title="Portfolio risk index"
            subtitle="Average score with level bands"
            loading={port.isLoading}
            error={port.error}
            empty={!trend?.items.length}
            demo={port.data?.demo_data}
            filename="risk-index"
            table={{
              columns: ["Period", "Risk index"],
              rows: (trend?.items ?? []).map((i) => ({
                Period: i.period,
                "Risk index": i.risk_index,
              })),
            }}
            option={
              trend?.items.length
                ? {
                    tooltip: { trigger: "axis" },
                    grid: { left: 48, right: 16, top: 16, bottom: 56 },
                    xAxis: {
                      type: "category",
                      data: trend.items.map((i) => i.period),
                      name: "Week",
                      nameLocation: "middle",
                      nameGap: 36,
                    },
                    yAxis: {
                      type: "value",
                      min: 0,
                      max: 100,
                      name: "Score (0 to 100)",
                      nameLocation: "middle",
                      nameGap: 34,
                      splitLine: { lineStyle: { color: "#94a3b833" } },
                    },
                    series: [
                      {
                        type: "line",
                        data: trend.items.map((i) => i.risk_index),
                        smooth: false,
                        showSymbol: false,
                        markLine: {
                          silent: true,
                          symbol: "none",
                          label: { formatter: "{b}" },
                          data: Object.entries(trend.bands).map(([k, v]) => ({
                            yAxis: v,
                            name: k,
                          })),
                          lineStyle: { type: "dashed", color: "#94a3b8" },
                        },
                      },
                    ],
                  }
                : undefined
            }
          />
        ) : (
          <Panel
            title="Events by type"
            actions={<span className="text-xs text-slate-600">Last 30 days</span>}
          >
            {events.isLoading ? (
              <SkeletonRows rows={4} />
            ) : byType.length ? (
              <ul className="space-y-2">
                {byType.map(([t, n]) => (
                  <li key={t} className="flex items-center gap-3 text-sm">
                    <span className="text-ink w-44">{label(t)}</span>
                    <span className="h-2 flex-1 rounded-full bg-slate-100">
                      <span
                        className="bg-chart-1 block h-2 rounded-full"
                        style={{ width: `${(100 * n) / (byType[0]?.[1] ?? 1)}%` }}
                      />
                    </span>
                    <span className="w-8 text-right font-mono text-slate-600">{n}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-600">
                No events linked to your suppliers in the last 30 days.
              </p>
            )}
          </Panel>
        )}
        <Panel
          title="Live alert feed"
          actions={
            <Link href="/app/alerts" className="text-link text-sm underline underline-offset-2">
              All alerts
            </Link>
          }
        >
          {alerts.isLoading ? (
            <SkeletonRows rows={4} />
          ) : alerts.error ? (
            <ErrorState error={alerts.error} />
          ) : alerts.data?.items.length ? (
            <ul className="divide-line divide-y">
              {alerts.data.items.slice(0, 6).map((a) => (
                <li key={a.id} className="flex items-start justify-between gap-3 py-2.5 text-sm">
                  <span>
                    <Link
                      href={`/app/suppliers/${a.supplier_id}`}
                      className="text-link font-medium underline underline-offset-2"
                    >
                      {a.supplier_name}
                    </Link>
                    <span className="block text-slate-600">{a.detail ?? label(a.kind)}</span>
                  </span>
                  <span className="shrink-0 text-xs text-slate-600">{ago(a.created_at)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-600">
              No alerts yet. New alerts appear here as they arrive.
            </p>
          )}
        </Panel>
      </div>

      {mgr && port.data && (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="Events by type"
            subtitle="Count by period"
            demo={port.data.demo_data}
            filename="events-by-type"
            empty={!port.data.events_by_type.length}
            table={{
              columns: ["Period", "Event type", "Events"],
              rows: port.data.events_by_type.map((e) => ({
                Period: e.period,
                "Event type": label(e.event_type),
                Events: e.events,
              })),
            }}
            option={(() => {
              const periods = [...new Set(port.data.events_by_type.map((e) => e.period))];
              const types = [...new Set(port.data.events_by_type.map((e) => e.event_type))];
              return {
                tooltip: { trigger: "axis" },
                legend: { bottom: 0, textStyle: { color: "#64748b" } },
                grid: { left: 48, right: 16, top: 16, bottom: 70 },
                xAxis: {
                  type: "category",
                  data: periods,
                  name: "Period",
                  nameLocation: "middle",
                  nameGap: 34,
                },
                yAxis: {
                  type: "value",
                  name: "Events",
                  minInterval: 1,
                  nameLocation: "middle",
                  nameGap: 32,
                  splitLine: { lineStyle: { color: "#94a3b833" } },
                },
                series: types.map((t) => ({
                  name: label(t),
                  type: "bar",
                  stack: "e",
                  data: periods.map(
                    (p) =>
                      port.data.events_by_type.find((e) => e.period === p && e.event_type === t)
                        ?.events ?? 0,
                  ),
                })),
              };
            })()}
          />
          <UsMapCard
            title="Recent events by state"
            subtitle="Severity-weighted event count, with facility events plotted"
            states={port.data.risk_by_state.map((s) => ({
              state: s.state,
              value: s.weighted_events,
            }))}
            points={port.data.facility_events.map((f) => ({
              name: f.title,
              lat: f.latitude,
              lon: f.longitude,
              value: f.severity,
            }))}
          />
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Panel title="Top risk suppliers">
          <DataTable<Supplier>
            id="overview-top"
            caption="Top risk suppliers"
            data={top}
            rowKey={(r) => r.id}
            loading={sup.isLoading}
            error={sup.error}
            empty="No scored suppliers yet."
            columns={[
              {
                header: "Supplier",
                accessorKey: "uploaded_name",
                cell: (c) => (
                  <Link
                    className="text-link font-medium underline underline-offset-2"
                    href={`/app/suppliers/${c.row.original.id}`}
                  >
                    {c.row.original.uploaded_name}
                  </Link>
                ),
              },
              {
                header: "Risk",
                accessorFn: (r) => Number(r.risk_score),
                cell: (c) => (
                  <RiskBadge level={c.row.original.risk_level} score={c.row.original.risk_score} />
                ),
              },
              { header: "Tier", accessorKey: "tier" },
            ]}
          />
        </Panel>
        <Panel title="Find a supplier">
          <p className="mb-3 text-sm text-slate-600">
            Press Ctrl K (Cmd K on a Mac) to search suppliers, companies, and pages from anywhere.
          </p>
          <p className="text-sm text-slate-600">
            Latest event:{" "}
            {events.data?.items[0]
              ? `${events.data.items[0].title} (${dateShort(events.data.items[0].reported_at)})`
              : "none in the last 30 days"}
          </p>
          <p className="mt-4 text-xs text-slate-600">
            Risk signals are leads for human review and not statements of fault.
          </p>
        </Panel>
      </div>
    </>
  );
}
