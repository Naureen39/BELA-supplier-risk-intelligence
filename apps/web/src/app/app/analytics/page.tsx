"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ChartCard } from "@/components/app/chart-card";
import { DataTable } from "@/components/app/data-table";
import { RangeBar, resolveRange, type Range } from "@/components/app/range-bar";
import { UsMapCard } from "@/components/app/us-map";
import { ErrorState, KpiCard, PageHeader, RiskBadge, SkeletonRows } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { dateTime, label, num, pct } from "@/lib/app/format";
import { qs } from "@/lib/app/hooks";
import type { Portfolio } from "@/lib/app/types";

interface Quality {
  demo_data: boolean;
  auto_resolution_rate: number;
  false_links: { per_1000: number | null; wrong_link_corrections: number };
  resolution_quality: {
    period: string;
    auto_resolved: number;
    reviewed: number;
    unresolved: number;
  }[];
  review_workload: {
    period: string;
    reviews_completed: number | null;
    median_review_minutes: number | null;
  }[];
  hybrid_vs_baselines: {
    data: string | null;
    systems: { system: string; false_links_per_1000: number | null }[];
  } | null;
  latency_throughput: {
    period: string;
    p50_ms: number;
    p95_ms: number;
    records_per_second: number | null;
  }[];
  routing: {
    total: number;
    links: { source: string; target: string; value: number }[];
    note: string;
  };
  data_freshness: {
    source: string;
    records: number;
    latest_record_at: string;
    age_days: number;
    status: string;
  }[];
  notes: string[];
}

const grid = { lineStyle: { color: "#94a3b833" } };
const fmtKpi = (k: { key: string; value: number | null; unit: string }) =>
  k.value == null
    ? "n/a"
    : k.unit === "percent"
      ? pct(k.value)
      : k.unit === "minutes"
        ? `${k.value.toFixed(0)} min`
        : num(k.value, k.unit === "score" ? 1 : k.unit === "per 1000" ? 1 : 0);

export default function AnalyticsPage() {
  const [r, setR] = useState<Range>({ preset: "90d", granularity: "week", compare: false });
  const [source, setSource] = useState("");
  const endQ = useQuery({
    queryKey: ["analytics-end"],
    queryFn: () => api<{ window: { to: string } }>("/analytics/portfolio?granularity=month"),
  });
  const end = endQ.data ? new Date(endQ.data.window.to) : new Date();
  const { from, to } = resolveRange(r, end);
  const params = qs({ from, to, granularity: r.granularity, compare: r.compare, source });
  const port = useQuery({
    queryKey: ["analytics", "portfolio", params],
    enabled: !!endQ.data,
    queryFn: () => api<Portfolio>(`/analytics/portfolio${params}`),
  });
  const qual = useQuery({
    queryKey: ["analytics", "quality", params],
    enabled: !!endQ.data,
    queryFn: () =>
      api<Quality>(`/analytics/quality${qs({ from, to, granularity: r.granularity })}`),
  });
  const p = port.data;
  const q = qual.data;
  const demo = p?.demo_data;

  if (endQ.isLoading) return <SkeletonRows rows={6} />;
  if (endQ.error) return <ErrorState error={endQ.error} retry={() => void endQ.refetch()} />;

  const periods = [...new Set((p?.events_by_type ?? []).map((e) => e.period))];
  const types = [...new Set((p?.events_by_type ?? []).map((e) => e.event_type))];
  const levels = ["low", "medium", "high", "critical"] as const;
  const levelColor = { low: "#1e8e5a", medium: "#e69f00", high: "#d9782d", critical: "#c0392b" };
  const conc = p?.concentration_by_parent.groups.slice(0, 10) ?? [];
  const tiers = [...new Set((p?.category_heatmap ?? []).map((h) => h.tier))];
  const cats = [...new Set((p?.category_heatmap ?? []).map((h) => h.event_type))];
  const rank: Record<string, number> = { low: 1, medium: 2, high: 3, critical: 4 };
  const nodeSet = [...new Set((q?.routing.links ?? []).flatMap((l) => [l.source, l.target]))];

  return (
    <>
      <PageHeader
        title="Analytics"
        text="Portfolio risk, event trends, resolution quality, and data freshness."
        demo={demo}
      />
      <RangeBar value={r} onChange={setR} asOf={p?.window.to} />
      <div className="mb-5 max-w-xs">
        <label htmlFor="src" className="mb-1 block text-xs font-medium text-slate-600">
          Event source
        </label>
        <select
          id="src"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="text-ink h-9 w-full rounded-[8px] border border-slate-300 bg-white px-2 text-sm"
        >
          <option value="">All sources</option>
          <option value="regulator">Regulators</option>
          <option value="news">News</option>
          {["epa_echo", "osha", "nhtsa", "cpsc", "openfda"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>
      {port.error ? (
        <ErrorState error={port.error} retry={() => void port.refetch()} />
      ) : (
        <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {port.isLoading
            ? Array.from({ length: 7 }, (_, i) => (
                <div
                  key={i}
                  className="h-24 animate-pulse rounded-[12px] bg-slate-200"
                  aria-hidden
                />
              ))
            : p?.kpis.map((k) => (
                <KpiCard
                  key={k.key}
                  label={k.label}
                  value={fmtKpi(k)}
                  change={k.change_pct}
                  better={k.better}
                />
              ))}
        </section>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Portfolio risk index"
          subtitle="Daily or periodic average with level bands"
          loading={port.isLoading}
          error={port.error}
          empty={!p?.risk_index_trend.items.length}
          demo={demo}
          filename="risk-index"
          table={{
            columns: ["Period", "Risk index"],
            rows: (p?.risk_index_trend.items ?? []).map((i) => ({
              Period: i.period,
              "Risk index": i.risk_index,
            })),
          }}
          option={
            p
              ? {
                  tooltip: { trigger: "axis" },
                  grid: { left: 48, right: 16, top: 16, bottom: 52 },
                  xAxis: {
                    type: "category",
                    data: p.risk_index_trend.items.map((i) => i.period),
                    name: "Period",
                    nameLocation: "middle",
                    nameGap: 34,
                  },
                  yAxis: {
                    type: "value",
                    min: 0,
                    max: 100,
                    name: "Score (0 to 100)",
                    nameLocation: "middle",
                    nameGap: 34,
                    splitLine: grid,
                  },
                  series: [
                    {
                      type: "line",
                      data: p.risk_index_trend.items.map((i) => i.risk_index),
                      showSymbol: false,
                      markArea: {
                        silent: true,
                        data: Object.entries(p.risk_index_trend.bands).map(([k, v], i, a) => [
                          {
                            yAxis: v,
                            name: k,
                            itemStyle: { color: ["#e69f0010", "#d9782d14", "#c0392b18"][i] },
                          },
                          { yAxis: a[i + 1]?.[1] ?? 100 },
                        ]),
                      },
                    },
                  ],
                }
              : undefined
          }
        />
        <ChartCard
          title="Suppliers by risk level"
          subtitle="Count over time"
          loading={port.isLoading}
          empty={!p?.suppliers_by_level_trend.length}
          demo={demo}
          filename="suppliers-by-level"
          table={{
            columns: ["Period", ...levels.map(label)],
            rows: (p?.suppliers_by_level_trend ?? []).map((x) => ({
              Period: x.period,
              Low: x.low,
              Medium: x.medium,
              High: x.high,
              Critical: x.critical,
            })),
          }}
          option={
            p
              ? {
                  tooltip: { trigger: "axis" },
                  legend: { bottom: 0, textStyle: { color: "#64748b" } },
                  grid: { left: 48, right: 16, top: 16, bottom: 70 },
                  xAxis: {
                    type: "category",
                    data: p.suppliers_by_level_trend.map((x) => x.period),
                    name: "Period",
                    nameLocation: "middle",
                    nameGap: 34,
                  },
                  yAxis: {
                    type: "value",
                    name: "Suppliers",
                    nameLocation: "middle",
                    nameGap: 34,
                    splitLine: grid,
                  },
                  series: levels.map((l) => ({
                    name: label(l),
                    type: "line",
                    stack: "s",
                    areaStyle: {},
                    showSymbol: false,
                    color: levelColor[l],
                    data: p.suppliers_by_level_trend.map((x) => x[l]),
                  })),
                }
              : undefined
          }
        />
        <ChartCard
          title="Events by type"
          subtitle="Count by period"
          loading={port.isLoading}
          empty={!periods.length}
          filename="events-by-type"
          table={{
            columns: ["Period", "Event type", "Events"],
            rows: (p?.events_by_type ?? []).map((e) => ({
              Period: e.period,
              "Event type": label(e.event_type),
              Events: e.events,
            })),
          }}
          option={
            p
              ? {
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
                    splitLine: grid,
                  },
                  series: types.map((t) => ({
                    name: label(t),
                    type: "bar",
                    stack: "e",
                    data: periods.map(
                      (pe) =>
                        p.events_by_type.find((e) => e.period === pe && e.event_type === t)
                          ?.events ?? 0,
                    ),
                  })),
                }
              : undefined
          }
        />
        <ChartCard
          title="Event source mix"
          subtitle="Regulators versus news"
          loading={port.isLoading}
          empty={!p?.event_source_mix.length}
          filename="source-mix"
          height={280}
          table={{
            columns: ["Source", "Events"],
            rows: (p?.event_source_mix ?? []).map((m) => ({
              Source: label(m.source_class),
              Events: m.events,
            })),
          }}
          option={
            p
              ? {
                  tooltip: { trigger: "item" },
                  legend: { bottom: 0, textStyle: { color: "#64748b" } },
                  series: [
                    {
                      type: "pie",
                      radius: ["45%", "70%"],
                      label: { formatter: "{b}: {c}" },
                      data: p.event_source_mix.map((m) => ({
                        name: label(m.source_class),
                        value: m.events,
                      })),
                    },
                  ],
                }
              : undefined
          }
        />
      </div>

      <div className="mt-6">
        <UsMapCard
          title="Risk by state"
          subtitle="Severity-weighted event count, with recent facility events plotted by coordinates"
          demo={demo}
          states={(p?.risk_by_state ?? []).map((s) => ({
            state: s.state,
            value: s.weighted_events,
          }))}
          points={(p?.facility_events ?? []).map((f) => ({
            name: f.title,
            lat: f.latitude,
            lon: f.longitude,
            value: f.severity,
          }))}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Category heatmap"
          subtitle="Supplier tier by event category. Color shows the highest risk level"
          loading={port.isLoading}
          empty={!p?.category_heatmap.length}
          filename="category-heatmap"
          table={{
            columns: ["Tier", "Category", "Events", "Highest level"],
            rows: (p?.category_heatmap ?? []).map((h) => ({
              Tier: label(h.tier),
              Category: label(h.event_type),
              Events: h.events,
              "Highest level": h.max_level ?? "n/a",
            })),
          }}
          option={
            p
              ? {
                  tooltip: {
                    formatter: (x: { data: number[] }) =>
                      `${tiers[x.data[1] ?? 0]} / ${cats[x.data[0] ?? 0]}: ${x.data[2]} events`,
                  },
                  grid: { left: 80, right: 16, top: 16, bottom: 90 },
                  xAxis: {
                    type: "category",
                    data: cats.map(label),
                    axisLabel: { rotate: 25, interval: 0 },
                    splitArea: { show: true },
                  },
                  yAxis: { type: "category", data: tiers.map(label) },
                  visualMap: {
                    min: 1,
                    max: 4,
                    show: false,
                    inRange: { color: ["#cfe8da", "#f3d9a4", "#eeb08a", "#d9786a"] },
                    dimension: 3,
                  },
                  series: [
                    {
                      type: "heatmap",
                      label: {
                        show: true,
                        formatter: (x: { data: number[] }) => String(x.data[2]),
                      },
                      data: p.category_heatmap.map((h) => [
                        cats.indexOf(h.event_type),
                        tiers.indexOf(h.tier),
                        h.events,
                        rank[h.max_level ?? "low"] ?? 1,
                      ]),
                    },
                  ],
                }
              : undefined
          }
        />
        <ChartCard
          title="Concentration by parent"
          subtitle="Share of suppliers and of high-risk suppliers under each parent"
          loading={port.isLoading}
          empty={!conc.length}
          filename="concentration-by-parent"
          table={{
            columns: ["Parent", "Suppliers", "Share", "High risk share", "Cumulative"],
            rows: conc.map((g) => ({
              Parent: g.name,
              Suppliers: g.suppliers,
              Share: pct(g.share_of_suppliers * 100),
              "High risk share": pct(g.share_of_high_risk * 100),
              Cumulative: pct(g.cumulative_share * 100),
            })),
          }}
          option={{
            tooltip: { trigger: "axis" },
            legend: { bottom: 0, textStyle: { color: "#64748b" } },
            grid: { left: 52, right: 52, top: 16, bottom: 96 },
            xAxis: {
              type: "category",
              data: conc.map((g) => g.name),
              axisLabel: { rotate: 25, interval: 0, width: 90, overflow: "truncate" },
            },
            yAxis: [
              {
                type: "value",
                name: "Share (%)",
                nameLocation: "middle",
                nameGap: 36,
                max: 100,
                splitLine: grid,
              },
              {
                type: "value",
                max: 100,
                name: "Cumulative (%)",
                nameLocation: "middle",
                nameGap: 36,
              },
            ],
            series: [
              {
                name: "Suppliers",
                type: "bar",
                data: conc.map((g) => +(g.share_of_suppliers * 100).toFixed(1)),
              },
              {
                name: "High-risk suppliers",
                type: "bar",
                data: conc.map((g) => +(g.share_of_high_risk * 100).toFixed(1)),
              },
              {
                name: "Cumulative",
                type: "line",
                yAxisIndex: 1,
                data: conc.map((g) => +(g.cumulative_share * 100).toFixed(1)),
              },
            ],
          }}
        />
      </div>

      <section className="mt-6" aria-labelledby="top-h">
        <h2 id="top-h" className="text-ink mb-3 text-base font-semibold">
          Top risk suppliers
        </h2>
        <DataTable<Portfolio["top_risk_suppliers"][number]>
          id="top-risk"
          caption="Top risk suppliers"
          exportName="top-risk-suppliers"
          data={p?.top_risk_suppliers ?? []}
          rowKey={(x) => x.supplier_id}
          loading={port.isLoading}
          error={port.error}
          empty="No scored suppliers."
          columns={[
            {
              header: "Supplier",
              accessorKey: "name",
              cell: (c) => (
                <Link
                  className="text-link font-medium underline underline-offset-2"
                  href={`/app/suppliers/${c.row.original.supplier_id}`}
                >
                  {c.row.original.name}
                </Link>
              ),
            },
            {
              header: "Risk",
              accessorFn: (x) => Number(x.score),
              cell: (c) => <RiskBadge level={c.row.original.level} score={c.row.original.score} />,
            },
            { header: "Last event", accessorFn: (x) => x.last_event?.title ?? "None" },
            {
              header: "Change in 30 days",
              accessorFn: (x) => x.change_30d ?? 0,
              cell: (c) =>
                c.row.original.change_30d == null
                  ? "n/a"
                  : `${c.row.original.change_30d >= 0 ? "+" : ""}${c.row.original.change_30d}`,
            },
            {
              header: "Trend",
              enableSorting: false,
              accessorFn: () => "",
              cell: (c) => {
                const v = (c.row.original.sparkline ?? []).map(Number);
                if (v.length < 2) return "n/a";
                const lo = Math.min(...v),
                  hi = Math.max(...v);
                return (
                  <svg viewBox="0 0 60 18" className="h-4 w-14" role="img" aria-label="Score trend">
                    <polyline
                      fill="none"
                      stroke="var(--color-chart-1)"
                      strokeWidth="1.6"
                      points={v
                        .map(
                          (x, i) =>
                            `${(i / (v.length - 1)) * 60},${hi === lo ? 9 : 16 - ((x - lo) / (hi - lo)) * 14}`,
                        )
                        .join(" ")}
                    />
                  </svg>
                );
              },
            },
          ]}
        />
      </section>

      <h2 className="text-ink mt-10 mb-4 text-xl font-semibold">Resolution quality</h2>
      {qual.error ? (
        <ErrorState error={qual.error} retry={() => void qual.refetch()} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="Resolution quality"
            subtitle="Auto-resolved, human-reviewed, and unresolved"
            loading={qual.isLoading}
            empty={!q?.resolution_quality.length}
            demo={q?.demo_data}
            filename="resolution-quality"
            table={{
              columns: ["Period", "Auto-resolved", "Reviewed", "Unresolved"],
              rows: (q?.resolution_quality ?? []).map((x) => ({
                Period: x.period,
                "Auto-resolved": x.auto_resolved,
                Reviewed: x.reviewed,
                Unresolved: x.unresolved,
              })),
            }}
            option={
              q
                ? {
                    tooltip: { trigger: "axis" },
                    legend: { bottom: 0, textStyle: { color: "#64748b" } },
                    grid: { left: 52, right: 16, top: 16, bottom: 70 },
                    xAxis: {
                      type: "category",
                      data: q.resolution_quality.map((x) => x.period),
                      name: "Period",
                      nameLocation: "middle",
                      nameGap: 34,
                    },
                    yAxis: {
                      type: "value",
                      name: "Suppliers",
                      nameLocation: "middle",
                      nameGap: 38,
                      splitLine: grid,
                    },
                    series: [
                      ["Auto-resolved", "auto_resolved"],
                      ["Reviewed", "reviewed"],
                      ["Unresolved", "unresolved"],
                    ].map(([n, k]) => ({
                      name: n,
                      type: "bar",
                      stack: "q",
                      data: q.resolution_quality.map((x) => x[k as "auto_resolved"]),
                    })),
                  }
                : undefined
            }
          />
          <ChartCard
            title="Review workload"
            subtitle="Reviews completed and median minutes"
            loading={qual.isLoading}
            empty={!q?.review_workload.length}
            demo={q?.demo_data}
            filename="review-workload"
            table={{
              columns: ["Period", "Reviews completed", "Median minutes"],
              rows: (q?.review_workload ?? []).map((x) => ({
                Period: x.period,
                "Reviews completed": x.reviews_completed ?? "n/a",
                "Median minutes": x.median_review_minutes ?? "n/a",
              })),
            }}
            option={
              q
                ? {
                    tooltip: { trigger: "axis" },
                    legend: { bottom: 0, textStyle: { color: "#64748b" } },
                    grid: { left: 52, right: 52, top: 16, bottom: 70 },
                    xAxis: {
                      type: "category",
                      data: q.review_workload.map((x) => x.period),
                      name: "Period",
                      nameLocation: "middle",
                      nameGap: 34,
                    },
                    yAxis: [
                      {
                        type: "value",
                        name: "Reviews",
                        nameLocation: "middle",
                        nameGap: 38,
                        splitLine: grid,
                      },
                      {
                        type: "value",
                        name: "Median minutes",
                        nameLocation: "middle",
                        nameGap: 38,
                      },
                    ],
                    series: [
                      {
                        name: "Reviews completed",
                        type: "bar",
                        data: q.review_workload.map((x) => x.reviews_completed),
                      },
                      {
                        name: "Median minutes",
                        type: "line",
                        yAxisIndex: 1,
                        data: q.review_workload.map((x) => x.median_review_minutes),
                      },
                    ],
                  }
                : undefined
            }
          />
          <ChartCard
            title="Hybrid versus baselines"
            subtitle={
              q?.hybrid_vs_baselines
                ? `False links per 1,000 records. Data: ${q.hybrid_vs_baselines.data ?? "not stated"}`
                : "False links per 1,000 records"
            }
            loading={qual.isLoading}
            empty={!q?.hybrid_vs_baselines?.systems.length}
            filename="hybrid-vs-baselines"
            table={{
              columns: ["System", "False links per 1,000"],
              rows: (q?.hybrid_vs_baselines?.systems ?? []).map((s) => ({
                System: s.system,
                "False links per 1,000": s.false_links_per_1000 ?? "n/a",
              })),
            }}
            option={
              q?.hybrid_vs_baselines
                ? {
                    tooltip: {},
                    grid: { left: 52, right: 16, top: 16, bottom: 52 },
                    xAxis: {
                      type: "category",
                      data: q.hybrid_vs_baselines.systems.map((s) => s.system),
                    },
                    yAxis: {
                      type: "value",
                      name: "False links per 1,000",
                      nameLocation: "middle",
                      nameGap: 38,
                      splitLine: grid,
                    },
                    series: [
                      {
                        type: "bar",
                        data: q.hybrid_vs_baselines.systems.map((s) => s.false_links_per_1000),
                        label: { show: true, position: "top" },
                      },
                    ],
                  }
                : undefined
            }
          />
          <ChartCard
            title="Latency and throughput"
            subtitle="Platform-wide, milliseconds and records per second"
            loading={qual.isLoading}
            empty={!q?.latency_throughput.length}
            demo
            filename="latency"
            table={{
              columns: ["Period", "p50 ms", "p95 ms", "Records per second"],
              rows: (q?.latency_throughput ?? []).map((x) => ({
                Period: x.period,
                "p50 ms": x.p50_ms,
                "p95 ms": x.p95_ms,
                "Records per second": x.records_per_second ?? "n/a",
              })),
            }}
            option={
              q
                ? {
                    tooltip: { trigger: "axis" },
                    legend: { bottom: 0, textStyle: { color: "#64748b" } },
                    grid: { left: 52, right: 52, top: 16, bottom: 70 },
                    xAxis: {
                      type: "category",
                      data: q.latency_throughput.map((x) => x.period),
                      name: "Period",
                      nameLocation: "middle",
                      nameGap: 34,
                    },
                    yAxis: [
                      {
                        type: "value",
                        name: "Milliseconds",
                        nameLocation: "middle",
                        nameGap: 38,
                        splitLine: grid,
                      },
                      {
                        type: "value",
                        name: "Records per second",
                        nameLocation: "middle",
                        nameGap: 38,
                      },
                    ],
                    series: [
                      {
                        name: "p50",
                        type: "line",
                        data: q.latency_throughput.map((x) => x.p50_ms),
                      },
                      {
                        name: "p95",
                        type: "line",
                        data: q.latency_throughput.map((x) => x.p95_ms),
                      },
                      {
                        name: "Records per second",
                        type: "line",
                        yAxisIndex: 1,
                        data: q.latency_throughput.map((x) => x.records_per_second),
                      },
                    ],
                  }
                : undefined
            }
          />
          <ChartCard
            title="Routing breakdown"
            subtitle="Where uploaded records went"
            loading={qual.isLoading}
            empty={!q?.routing.links.length}
            filename="routing"
            table={{
              columns: ["From", "To", "Records"],
              rows: (q?.routing.links ?? []).map((l) => ({
                From: l.source,
                To: l.target,
                Records: l.value,
              })),
            }}
            option={
              q
                ? {
                    tooltip: { trigger: "item" },
                    series: [
                      {
                        type: "sankey",
                        left: 8,
                        right: 100,
                        data: nodeSet.map((n) => ({ name: n })),
                        links: q.routing.links,
                        label: { color: "#64748b" },
                        emphasis: { focus: "adjacency" },
                      },
                    ],
                  }
                : undefined
            }
          />
        </div>
      )}
      <section aria-labelledby="fresh-h" className="mt-6">
        <h2 id="fresh-h" className="text-ink mb-3 text-base font-semibold">
          Data freshness
        </h2>
        <DataTable<Quality["data_freshness"][number]>
          id="freshness"
          caption="Data freshness by source"
          exportName="data-freshness"
          data={q?.data_freshness ?? []}
          rowKey={(x) => x.source}
          loading={qual.isLoading}
          empty="No events have been loaded."
          columns={[
            { header: "Source", accessorKey: "source" },
            { header: "Records", accessorKey: "records" },
            {
              header: "Latest record",
              accessorKey: "latest_record_at",
              cell: (c) => dateTime(c.row.original.latest_record_at),
            },
            { header: "Age in days", accessorKey: "age_days" },
            {
              header: "Status",
              accessorKey: "status",
              cell: (c) => (
                <Badge
                  tone={
                    c.row.original.status === "fresh"
                      ? "success"
                      : c.row.original.status === "aging"
                        ? "warning"
                        : "danger"
                  }
                >
                  {label(c.row.original.status)}
                </Badge>
              ),
            },
          ]}
        />
      </section>
      <ul className="mt-4 space-y-1 text-xs text-slate-600">
        {[
          ...(p?.notes ?? []),
          ...(q?.notes ?? []),
          "Risk signals are leads for human review and not statements of fault.",
        ].map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </>
  );
}
