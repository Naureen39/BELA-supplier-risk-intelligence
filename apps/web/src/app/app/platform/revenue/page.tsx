"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ChartCard } from "@/components/app/chart-card";
import { DataTable } from "@/components/app/data-table";
import { RangeBar, resolveRange, type Range } from "@/components/app/range-bar";
import { ErrorState, KpiCard, PageHeader, Panel } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { dateShort, label, num, pct, usd } from "@/lib/app/format";
import { qs } from "@/lib/app/hooks";
import { can, useMe } from "@/lib/app/session";
import type { Kpi } from "@/lib/app/types";

const grid = { lineStyle: { color: "#94a3b833" } };
const PLAN_COLOR: Record<string, string> = {
  starter: "#2f74d8",
  professional: "#00a3a3",
  enterprise: "#8e5bd9",
};
interface Meta {
  demo_data: boolean;
  data_as_of: { views_refreshed_at: string | null; data_through: string | null };
}
interface Cust {
  id: string;
  name: string;
  industry: string | null;
  region: string | null;
  plan_code: string | null;
  mrr: number;
  arr: number;
  supplier_limit: number | null;
  monitored_suppliers: number | null;
  last_activity: string | null;
  health: string;
  mrr_trend: number[] | null;
}
const unitFmt = (k: Kpi) =>
  k.value == null
    ? "n/a"
    : k.unit === "usd"
      ? usd(k.value)
      : k.unit === "percent"
        ? pct(k.value)
        : k.unit === "months"
          ? `${k.value.toFixed(1)} months`
          : k.unit === "ratio"
            ? k.value.toFixed(1)
            : num(k.value);

function Drill({ id, onClose }: { id: string; onClose: () => void }) {
  const d = useQuery({
    queryKey: ["cust", id],
    queryFn: () =>
      api<{
        tenant: { name: string; industry: string | null; region: string | null };
        subscriptions: {
          plan_code: string;
          billing_cycle: string;
          price: number;
          started_on: string;
          ended_on: string | null;
          change_reason: string | null;
        }[];
        invoices: { period_month: string; status: string; total: number }[];
        usage: { day: string; monitored_suppliers: number; api_calls: number }[];
      }>(`/platform/revenue/customers/${id}`),
  });
  return (
    <Dialog.Root open onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-[min(96vw,520px)] space-y-5 overflow-y-auto bg-white p-6 shadow-[var(--shadow-3)]">
          <Dialog.Title className="text-ink text-lg font-semibold">
            {d.data?.tenant.name ?? "Customer"}
          </Dialog.Title>
          <Dialog.Description className="text-sm text-slate-600">
            Subscription history, invoices, and usage. Demo data.
          </Dialog.Description>
          {d.isLoading ? (
            <p>Loading</p>
          ) : d.error ? (
            <ErrorState error={d.error} />
          ) : (
            d.data && (
              <>
                <section aria-label="Subscriptions">
                  <h3 className="text-ink mb-2 text-sm font-semibold">Subscriptions</h3>
                  <ul className="space-y-1 text-sm">
                    {d.data.subscriptions.map((s, i) => (
                      <li key={i} className="text-slate-700">
                        {label(s.plan_code)} ({s.billing_cycle}), {usd(s.price)} from{" "}
                        {dateShort(s.started_on)}
                        {s.ended_on ? ` to ${dateShort(s.ended_on)}` : ""}
                        {s.change_reason ? `, ${s.change_reason}` : ""}
                      </li>
                    ))}
                  </ul>
                </section>
                <section aria-label="Invoices">
                  <h3 className="text-ink mb-2 text-sm font-semibold">Recent invoices</h3>
                  <ul className="space-y-1 text-sm">
                    {d.data.invoices.slice(0, 8).map((i, k) => (
                      <li key={k} className="flex justify-between text-slate-700">
                        <span>{dateShort(i.period_month)}</span>
                        <span>
                          {usd(i.total, 2)}{" "}
                          <Badge
                            tone={
                              i.status === "paid"
                                ? "success"
                                : i.status === "open"
                                  ? "neutral"
                                  : "danger"
                            }
                          >
                            {i.status}
                          </Badge>
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
                <ChartCard
                  title="Usage"
                  subtitle="Monitored suppliers, last 90 days"
                  demo
                  height={200}
                  filename="customer-usage"
                  table={{
                    columns: ["Day", "Monitored", "API calls"],
                    rows: d.data.usage.map((u) => ({
                      Day: u.day,
                      Monitored: u.monitored_suppliers,
                      "API calls": u.api_calls,
                    })),
                  }}
                  empty={!d.data.usage.length}
                  option={{
                    tooltip: { trigger: "axis" },
                    grid: { left: 52, right: 12, top: 10, bottom: 40 },
                    xAxis: {
                      type: "category",
                      data: d.data.usage.map((u) => u.day),
                      name: "Day",
                      nameLocation: "middle",
                      nameGap: 26,
                    },
                    yAxis: {
                      type: "value",
                      name: "Suppliers",
                      nameLocation: "middle",
                      nameGap: 38,
                      splitLine: grid,
                    },
                    series: [
                      {
                        type: "line",
                        showSymbol: false,
                        data: d.data.usage.map((u) => u.monitored_suppliers),
                      },
                    ],
                  }}
                />
              </>
            )
          )}
          <Dialog.Close asChild>
            <Button variant="secondary">Close</Button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function RevenuePage() {
  const me = useMe().data;
  const [r, setR] = useState<Range>({ preset: "12m", granularity: "month", compare: true });
  const [plan, setPlan] = useState("");
  const [region, setRegion] = useState("");
  const [industry, setIndustry] = useState("");
  const [drill, setDrill] = useState<string | null>(null);
  const summary = useQuery({
    queryKey: ["rev", "summary"],
    queryFn: () => api<{ month: string }>("/platform/revenue/summary"),
  });
  const end = summary.data?.month ? new Date(summary.data.month) : new Date();
  const lastDay = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() + 1, 0));
  const { from, to } = resolveRange(r, lastDay);
  const f = qs({ from, to, compare: r.compare, plan, region, industry });
  const useRev = <T,>(key: string, path: string, extra = "") =>
    useQuery({
      queryKey: ["rev", key, f, extra],
      enabled: !!summary.data,
      queryFn: () => api<T & Meta>(`/platform/revenue/${path}${f}${extra}`),
    });
  const kpis = useRev<{ month: string; items: Kpi[] }>("kpis", "kpis");
  const mrr = useRev<{
    items: { month_start: string; plan_code: string; mrr: number }[];
    annotations: { day: string; label: string }[];
  }>("mrr", "mrr");
  const mv = useRev<{
    items: {
      month_start: string;
      new_mrr: number;
      expansion_mrr: number;
      contraction_mrr: number;
      churn_mrr: number;
      net_new_mrr: number;
    }[];
  }>("mv", "movements");
  const mix = useRev<{
    items: { month_start: string; subscription: number; overage: number; credit: number }[];
  }>("mix", "mix");
  const fc = useRev<{
    history: { month_start: string; mrr: number }[];
    forecast: { month_start: string; mean: number; lower: number; upper: number }[];
    model: string;
    backtest: { mape_pct: number; interval_coverage_pct: number } | null;
    note: string;
  }>("fc", "forecast");
  const coh = useRev<{
    items: { cohort_month: string; months_since_signup: number; retention_pct: number }[];
  }>("coh", "cohorts");
  const bReg = useRev<{ items: { value: string; arr: number; share_pct: number }[] }>(
    "breg",
    "breakdown",
    "&dimension=region",
  );
  const bInd = useRev<{ items: { value: string; arr: number; share_pct: number }[] }>(
    "bind",
    "breakdown",
    "&dimension=industry",
  );
  const bPlan = useRev<{ items: { value: string; arr: number; share_pct: number }[] }>(
    "bplan",
    "breakdown",
    "&dimension=plan",
  );
  const conc = useRev<{
    items: { name: string; arr: number; share_pct: number; cumulative_share_pct: number }[];
    top_share_pct: number;
  }>("conc", "concentration");
  const ue = useRev<{
    items: {
      month_start: string;
      cac: number | null;
      ltv: number | null;
      ltv_to_cac: number | null;
    }[];
    note: string;
  }>("ue", "unit-economics");
  const bill = useRev<{
    as_of: string | null;
    buckets: { bucket: string; invoices: number; amount: number }[];
    items: {
      id: number;
      name: string;
      period_month: string;
      status: string;
      total: number;
      days_overdue: number;
      days_outstanding: number;
    }[];
  }>("bill", "billing-health");
  const cust = useRev<{ total: number; items: Cust[] }>("cust", "customers", "&limit=25");

  if (!can(me, "view_revenue"))
    return <ErrorState error={new Error("You do not have access to the revenue dashboard.")} />;
  if (summary.error)
    return <ErrorState error={summary.error} retry={() => void summary.refetch()} />;

  const months = [...new Set((mrr.data?.items ?? []).map((i) => i.month_start))];
  const plans = [...new Set((mrr.data?.items ?? []).map((i) => i.plan_code))];
  const total = months.map((m) =>
    (mrr.data?.items ?? []).filter((i) => i.month_start === m).reduce((a, i) => a + i.mrr, 0),
  );
  const hist = fc.data?.history ?? [];
  const fmonths = [
    ...hist.map((h) => h.month_start),
    ...(fc.data?.forecast ?? []).map((x) => x.month_start),
  ];
  const cohorts = [...new Set((coh.data?.items ?? []).map((c) => c.cohort_month))];
  const maxAge = Math.max(0, ...(coh.data?.items ?? []).map((c) => c.months_since_signup));
  const bars = (
    key: string,
    items: { value: string; arr: number }[] | undefined,
    setter: (v: string) => void,
    t: string,
    color?: (v: string) => string,
  ) => (
    <ChartCard
      title={t}
      subtitle="Click a bar to filter the page"
      loading={!items}
      empty={!items?.length}
      demo
      filename={key}
      onPick={setter}
      table={{
        columns: ["Name", "ARR"],
        rows: (items ?? []).map((i) => ({ Name: label(i.value), ARR: usd(i.arr) })),
      }}
      option={
        items?.length
          ? {
              tooltip: {
                formatter: (x: { name: string; value: number }) => `${x.name}: ${usd(x.value)}`,
              },
              grid: { left: 150, right: 56, top: 8, bottom: 36 },
              xAxis: {
                type: "value",
                name: "ARR (USD)",
                nameLocation: "middle",
                nameGap: 26,
                splitLine: grid,
                axisLabel: { formatter: (v: number) => `${v / 1000}k` },
              },
              yAxis: { type: "category", inverse: true, data: items.map((i) => label(i.value)) },
              series: [
                {
                  type: "bar",
                  data: items.map((i) => ({
                    value: i.arr,
                    name: i.value,
                    itemStyle: color ? { color: color(i.value) } : undefined,
                  })),
                  label: {
                    show: true,
                    position: "right",
                    formatter: (x: { value: number }) => usd(x.value / 1000) + "k",
                  },
                },
              ],
            }
          : undefined
      }
    />
  );

  return (
    <>
      <PageHeader
        title="Revenue"
        text="Recurring revenue, retention, and unit economics for the platform."
        demo
      />
      <RangeBar
        value={r}
        onChange={setR}
        granularities={["month"]}
        asOf={
          kpis.data?.data_as_of.data_through
            ? `${kpis.data.data_as_of.data_through}${kpis.data.data_as_of.views_refreshed_at ? ` (views refreshed ${dateShort(kpis.data.data_as_of.views_refreshed_at)})` : ""}`
            : undefined
        }
      />
      {(plan || region || industry) && (
        <p className="text-ink mb-4 flex flex-wrap items-center gap-2 text-sm" role="status">
          Filters:
          {[
            ["Plan", plan, setPlan],
            ["Region", region, setRegion],
            ["Industry", industry, setIndustry],
          ].map(([n, v, s]) =>
            v ? (
              <button
                key={String(n)}
                type="button"
                onClick={() => (s as (x: string) => void)("")}
                className="bg-brand-100 text-link rounded-full px-3 py-1"
              >
                {String(n)}: {label(String(v))} (clear)
              </button>
            ) : null,
          )}
        </p>
      )}
      <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {kpis.error ? (
          <div className="col-span-full">
            <ErrorState error={kpis.error} />
          </div>
        ) : kpis.isLoading ? (
          Array.from({ length: 10 }, (_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-[12px] bg-slate-200" aria-hidden />
          ))
        ) : (
          kpis.data?.items.map((k) => (
            <KpiCard
              key={k.key}
              label={k.label}
              value={unitFmt(k)}
              change={k.change_pct}
              better={k.better}
              sparkline={k.sparkline}
            />
          ))
        )}
      </section>
      <p className="mt-2 text-xs text-slate-600">
        CAC payback assumes a fixed 80 percent gross margin, and CAC is shown only without filters.
      </p>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="MRR over time"
          subtitle="By plan, with the total and business events"
          loading={mrr.isLoading}
          error={mrr.error}
          empty={!months.length}
          demo
          filename="mrr"
          height={320}
          table={{
            columns: ["Month", ...plans.map(label), "Total"],
            rows: months.map((m, i) => ({
              Month: m,
              ...Object.fromEntries(
                plans.map((p) => [
                  label(p),
                  (mrr.data?.items ?? []).find((x) => x.month_start === m && x.plan_code === p)
                    ?.mrr ?? 0,
                ]),
              ),
              Total: total[i],
            })),
          }}
          option={{
            tooltip: { trigger: "axis", valueFormatter: (v: number) => usd(v) },
            legend: { bottom: 0, textStyle: { color: "#64748b" } },
            grid: { left: 64, right: 16, top: 16, bottom: 70 },
            xAxis: {
              type: "category",
              data: months,
              name: "Month",
              nameLocation: "middle",
              nameGap: 34,
            },
            yAxis: {
              type: "value",
              name: "MRR (USD)",
              nameLocation: "middle",
              nameGap: 50,
              splitLine: grid,
            },
            series: [
              ...plans.map((p, i) => ({
                name: label(p),
                type: "line",
                stack: "m",
                areaStyle: {},
                showSymbol: false,
                color: PLAN_COLOR[p],
                data: months.map(
                  (m) =>
                    (mrr.data?.items ?? []).find((x) => x.month_start === m && x.plan_code === p)
                      ?.mrr ?? 0,
                ),
                ...(i === 0
                  ? {
                      markLine: {
                        silent: true,
                        symbol: "none",
                        lineStyle: { type: "dashed", color: "#94a3b8" },
                        label: { show: false },
                        data: (mrr.data?.annotations ?? []).map((a) => ({
                          xAxis: a.day.slice(0, 7) + "-01",
                          name: a.label,
                        })),
                      },
                    }
                  : {}),
              })),
              {
                name: "Total",
                type: "line",
                showSymbol: false,
                lineStyle: { color: "#0b1b33", width: 2 },
                color: "#0b1b33",
                data: total,
              },
            ],
          }}
        />
        <ChartCard
          title="MRR movements"
          subtitle="New, expansion, contraction, churn, and net new"
          loading={mv.isLoading}
          error={mv.error}
          empty={!mv.data?.items.length}
          demo
          filename="mrr-movements"
          height={320}
          table={{
            columns: ["Month", "New", "Expansion", "Contraction", "Churn", "Net new"],
            rows: (mv.data?.items ?? []).map((m) => ({
              Month: m.month_start,
              New: m.new_mrr,
              Expansion: m.expansion_mrr,
              Contraction: -m.contraction_mrr,
              Churn: -m.churn_mrr,
              "Net new": m.net_new_mrr,
            })),
          }}
          option={
            mv.data
              ? {
                  tooltip: { trigger: "axis", valueFormatter: (v: number) => usd(v) },
                  legend: { bottom: 0, textStyle: { color: "#64748b" } },
                  grid: { left: 64, right: 16, top: 16, bottom: 70 },
                  xAxis: {
                    type: "category",
                    data: mv.data.items.map((m) => m.month_start),
                    name: "Month",
                    nameLocation: "middle",
                    nameGap: 34,
                  },
                  yAxis: {
                    type: "value",
                    name: "MRR change (USD)",
                    nameLocation: "middle",
                    nameGap: 50,
                    splitLine: grid,
                  },
                  series: [
                    {
                      name: "New",
                      type: "bar",
                      stack: "x",
                      data: mv.data.items.map((m) => m.new_mrr),
                    },
                    {
                      name: "Expansion",
                      type: "bar",
                      stack: "x",
                      data: mv.data.items.map((m) => m.expansion_mrr),
                    },
                    {
                      name: "Contraction",
                      type: "bar",
                      stack: "x",
                      data: mv.data.items.map((m) => -m.contraction_mrr),
                    },
                    {
                      name: "Churn",
                      type: "bar",
                      stack: "x",
                      data: mv.data.items.map((m) => -m.churn_mrr),
                    },
                    {
                      name: "Net new",
                      type: "line",
                      color: "#0b1b33",
                      data: mv.data.items.map((m) => m.net_new_mrr),
                    },
                  ],
                }
              : undefined
          }
        />
        <ChartCard
          title="Revenue mix"
          subtitle="Invoiced subscription fees, overage, and credits. Overage is not MRR"
          loading={mix.isLoading}
          error={mix.error}
          empty={!mix.data?.items.length}
          demo
          filename="revenue-mix"
          table={{
            columns: ["Month", "Subscription", "Overage", "Credit"],
            rows: (mix.data?.items ?? []).map((m) => ({
              Month: m.month_start,
              Subscription: m.subscription,
              Overage: m.overage,
              Credit: m.credit,
            })),
          }}
          option={
            mix.data
              ? {
                  tooltip: { trigger: "axis", valueFormatter: (v: number) => usd(v) },
                  legend: { bottom: 0, textStyle: { color: "#64748b" } },
                  grid: { left: 64, right: 16, top: 16, bottom: 70 },
                  xAxis: {
                    type: "category",
                    data: mix.data.items.map((m) => m.month_start),
                    name: "Month",
                    nameLocation: "middle",
                    nameGap: 34,
                  },
                  yAxis: {
                    type: "value",
                    name: "Invoiced (USD)",
                    nameLocation: "middle",
                    nameGap: 50,
                    splitLine: grid,
                  },
                  series: [
                    {
                      name: "Subscription",
                      type: "bar",
                      stack: "m",
                      data: mix.data.items.map((m) => m.subscription),
                    },
                    {
                      name: "Overage",
                      type: "bar",
                      stack: "m",
                      data: mix.data.items.map((m) => m.overage),
                    },
                  ],
                }
              : undefined
          }
        />
        <ChartCard
          title="Forecast"
          subtitle={
            fc.data
              ? `${fc.data.model}. Estimate with an 80 percent interval. Backtest MAPE ${fc.data.backtest?.mape_pct ?? "n/a"} percent, interval coverage ${fc.data.backtest?.interval_coverage_pct ?? "n/a"} percent.`
              : "Estimate"
          }
          loading={fc.isLoading}
          error={fc.error}
          empty={!hist.length}
          demo
          filename="forecast"
          table={{
            columns: ["Month", "MRR", "Forecast", "Lower", "Upper"],
            rows: [
              ...hist.map((h) => ({
                Month: h.month_start,
                MRR: h.mrr,
                Forecast: "",
                Lower: "",
                Upper: "",
              })),
              ...(fc.data?.forecast ?? []).map((x) => ({
                Month: x.month_start,
                MRR: "",
                Forecast: x.mean,
                Lower: x.lower,
                Upper: x.upper,
              })),
            ],
          }}
          option={
            fc.data
              ? {
                  tooltip: { trigger: "axis", valueFormatter: (v: number) => usd(v) },
                  legend: { bottom: 0, textStyle: { color: "#64748b" } },
                  grid: { left: 64, right: 16, top: 16, bottom: 70 },
                  xAxis: {
                    type: "category",
                    data: fmonths,
                    name: "Month",
                    nameLocation: "middle",
                    nameGap: 34,
                  },
                  yAxis: {
                    type: "value",
                    name: "MRR (USD)",
                    nameLocation: "middle",
                    nameGap: 50,
                    scale: true,
                    splitLine: grid,
                  },
                  series: [
                    {
                      name: "MRR",
                      type: "line",
                      showSymbol: false,
                      data: [...hist.map((h) => h.mrr), ...fc.data.forecast.map(() => null)],
                    },
                    {
                      name: "Lower",
                      type: "line",
                      stack: "band",
                      lineStyle: { opacity: 0 },
                      showSymbol: false,
                      data: [...hist.map(() => null), ...fc.data.forecast.map((x) => x.lower)],
                    },
                    {
                      name: "80% interval",
                      type: "line",
                      stack: "band",
                      lineStyle: { opacity: 0 },
                      areaStyle: { opacity: 0.2 },
                      showSymbol: false,
                      data: [
                        ...hist.map(() => null),
                        ...fc.data.forecast.map((x) => x.upper - x.lower),
                      ],
                    },
                    {
                      name: "Forecast (estimate)",
                      type: "line",
                      lineStyle: { type: "dashed" },
                      showSymbol: false,
                      data: [
                        ...hist.map((h, i) => (i === hist.length - 1 ? h.mrr : null)),
                        ...fc.data.forecast.map((x) => x.mean),
                      ],
                    },
                  ],
                }
              : undefined
          }
        />
        <ChartCard
          title="Cohort retention"
          subtitle="Revenue retention by signup month and months since signup (percent)"
          loading={coh.isLoading}
          error={coh.error}
          empty={!cohorts.length}
          demo
          filename="cohorts"
          height={340}
          table={{
            columns: ["Cohort", "Months since signup", "Retention (%)"],
            rows: (coh.data?.items ?? []).map((c) => ({
              Cohort: c.cohort_month,
              "Months since signup": c.months_since_signup,
              "Retention (%)": c.retention_pct,
            })),
          }}
          option={
            coh.data
              ? {
                  tooltip: {
                    formatter: (x: { data: number[] }) =>
                      `${cohorts[x.data[1] ?? 0]}, month ${x.data[0]}: ${x.data[2]}%`,
                  },
                  grid: { left: 80, right: 16, top: 8, bottom: 64 },
                  xAxis: {
                    type: "category",
                    data: Array.from({ length: maxAge + 1 }, (_, i) => i),
                    name: "Months since signup",
                    nameLocation: "middle",
                    nameGap: 30,
                  },
                  yAxis: { type: "category", data: cohorts, inverse: true },
                  visualMap: {
                    min: 40,
                    max: 160,
                    orient: "horizontal",
                    left: "center",
                    bottom: 0,
                    text: ["160", "40"],
                    inRange: { color: ["#d55e5e", "#f3d9a4", "#2f74d8"] },
                    calculable: false,
                  },
                  series: [
                    {
                      type: "heatmap",
                      data: coh.data.items.map((c) => [
                        c.months_since_signup,
                        cohorts.indexOf(c.cohort_month),
                        c.retention_pct,
                      ]),
                    },
                  ],
                }
              : undefined
          }
        />
        {bars("arr-by-region", bReg.data?.items, setRegion, "ARR by region")}
        {bars("arr-by-industry", bInd.data?.items, setIndustry, "ARR by industry")}
        {bars(
          "arr-by-plan",
          bPlan.data?.items,
          setPlan,
          "ARR by plan",
          (v) => PLAN_COLOR[v] ?? "#6c7a89",
        )}
        <ChartCard
          title="Customer concentration"
          subtitle={`Top 10 customers by ARR. Top 10 hold ${pct(conc.data?.top_share_pct)} of ARR`}
          loading={conc.isLoading}
          error={conc.error}
          empty={!conc.data?.items.length}
          demo
          filename="concentration"
          table={{
            columns: ["Customer", "ARR", "Share", "Cumulative"],
            rows: (conc.data?.items ?? []).map((c) => ({
              Customer: c.name,
              ARR: usd(c.arr),
              Share: pct(c.share_pct),
              Cumulative: pct(c.cumulative_share_pct),
            })),
          }}
          option={
            conc.data
              ? {
                  tooltip: { trigger: "axis" },
                  legend: { bottom: 0, textStyle: { color: "#64748b" } },
                  grid: { left: 52, right: 52, top: 16, bottom: 96 },
                  xAxis: {
                    type: "category",
                    data: conc.data.items.map((c) => c.name),
                    axisLabel: { rotate: 30, interval: 0, width: 90, overflow: "truncate" },
                  },
                  yAxis: [
                    {
                      type: "value",
                      name: "Share of ARR (%)",
                      nameLocation: "middle",
                      nameGap: 36,
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
                    { name: "Share", type: "bar", data: conc.data.items.map((c) => c.share_pct) },
                    {
                      name: "Cumulative",
                      type: "line",
                      yAxisIndex: 1,
                      data: conc.data.items.map((c) => c.cumulative_share_pct),
                    },
                  ],
                }
              : undefined
          }
        />
        <ChartCard
          title="Unit economics"
          subtitle={ue.data?.note ?? "CAC, LTV, and LTV to CAC"}
          loading={ue.isLoading}
          error={ue.error}
          empty={!ue.data?.items.length}
          demo
          filename="unit-economics"
          table={{
            columns: ["Month", "CAC", "LTV", "LTV to CAC"],
            rows: (ue.data?.items ?? []).map((u) => ({
              Month: u.month_start,
              CAC: u.cac ?? "n/a",
              LTV: u.ltv ?? "n/a",
              "LTV to CAC": u.ltv_to_cac ?? "n/a",
            })),
          }}
          option={
            ue.data
              ? {
                  tooltip: { trigger: "axis" },
                  legend: { bottom: 0, textStyle: { color: "#64748b" } },
                  grid: { left: 64, right: 56, top: 16, bottom: 70 },
                  xAxis: {
                    type: "category",
                    data: ue.data.items.map((u) => u.month_start),
                    name: "Month",
                    nameLocation: "middle",
                    nameGap: 34,
                  },
                  yAxis: [
                    {
                      type: "value",
                      name: "USD",
                      nameLocation: "middle",
                      nameGap: 50,
                      splitLine: grid,
                    },
                    { type: "value", name: "LTV to CAC", nameLocation: "middle", nameGap: 36 },
                  ],
                  series: [
                    { name: "CAC", type: "bar", data: ue.data.items.map((u) => u.cac) },
                    { name: "LTV", type: "bar", data: ue.data.items.map((u) => u.ltv) },
                    {
                      name: "LTV to CAC",
                      type: "line",
                      yAxisIndex: 1,
                      data: ue.data.items.map((u) => u.ltv_to_cac),
                    },
                  ],
                }
              : undefined
          }
        />
      </div>

      <h2 className="text-ink mt-10 mb-3 text-xl font-semibold">Billing health</h2>
      <Panel>
        {bill.error ? (
          <ErrorState error={bill.error} />
        ) : (
          <>
            <p className="mb-3 text-sm text-slate-600">
              Open and overdue invoices as of {dateShort(bill.data?.as_of)} (the latest invoice date
              in the data).
            </p>
            <ul className="mb-4 flex flex-wrap gap-3">
              {bill.data?.buckets.map((b) => (
                <li key={b.bucket} className="rounded-[10px] bg-slate-50 px-3 py-2 text-sm">
                  <span className="block text-xs text-slate-600">
                    {b.bucket === "current" ? "Not yet due" : `${b.bucket} days overdue`}
                  </span>
                  <span className="text-ink font-semibold">{usd(b.amount)}</span>{" "}
                  <span className="text-slate-600">({b.invoices})</span>
                </li>
              ))}
            </ul>
            <DataTable<NonNullable<typeof bill.data>["items"][number]>
              id="billing-health"
              caption="Open and overdue invoices"
              exportName="billing-health"
              data={bill.data?.items ?? []}
              rowKey={(i) => String(i.id)}
              loading={bill.isLoading}
              empty="No open or overdue invoices."
              columns={[
                { header: "Customer", accessorKey: "name" },
                { header: "Period", accessorFn: (i) => dateShort(i.period_month) },
                {
                  header: "Amount",
                  accessorKey: "total",
                  cell: (c) => usd(c.row.original.total, 2),
                },
                { header: "Days outstanding", accessorKey: "days_outstanding" },
                {
                  header: "Status",
                  accessorKey: "status",
                  cell: (c) => (
                    <Badge tone={c.row.original.status === "overdue" ? "danger" : "neutral"}>
                      {label(c.row.original.status)}
                    </Badge>
                  ),
                },
              ]}
            />
          </>
        )}
      </Panel>

      <h2 className="text-ink mt-10 mb-3 text-xl font-semibold">Customers</h2>
      <DataTable<Cust>
        id="customers"
        caption="Customers"
        exportName="customers"
        data={cust.data?.items ?? []}
        rowKey={(c) => c.id}
        loading={cust.isLoading}
        error={cust.error}
        empty="No customers."
        onRowClick={(c) => setDrill(c.id)}
        columns={[
          {
            header: "Customer",
            accessorKey: "name",
            cell: (c) => (
              <button
                type="button"
                className="text-link font-medium underline underline-offset-2"
                onClick={(e) => {
                  e.stopPropagation();
                  setDrill(c.row.original.id);
                }}
              >
                {c.row.original.name}
              </button>
            ),
          },
          {
            header: "Plan",
            accessorFn: (c) => c.plan_code ?? "",
            cell: (c) => (c.row.original.plan_code ? label(c.row.original.plan_code) : "n/a"),
          },
          { header: "MRR", accessorKey: "mrr", cell: (c) => usd(c.row.original.mrr) },
          {
            header: "Suppliers vs limit",
            accessorFn: (c) => c.monitored_suppliers ?? 0,
            cell: (c) =>
              `${num(c.row.original.monitored_suppliers)} of ${num(c.row.original.supplier_limit)}`,
          },
          {
            header: "Last activity",
            accessorFn: (c) => c.last_activity ?? "",
            cell: (c) => dateShort(c.row.original.last_activity),
          },
          {
            header: "Trend",
            enableSorting: false,
            accessorFn: () => "",
            cell: (c) => {
              const v = c.row.original.mrr_trend ?? [];
              if (v.length < 2) return "n/a";
              const lo = Math.min(...v),
                hi = Math.max(...v);
              return (
                <svg viewBox="0 0 60 18" className="h-4 w-14" role="img" aria-label="MRR trend">
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
          {
            header: "Health",
            accessorKey: "health",
            cell: (c) => (
              <Badge
                tone={
                  c.row.original.health === "healthy"
                    ? "success"
                    : c.row.original.health === "churned"
                      ? "neutral"
                      : "warning"
                }
              >
                {label(c.row.original.health)}
              </Badge>
            ),
          },
        ]}
      />
      <p className="mt-3 text-xs text-slate-600">
        Showing the top 25 customers by MRR of {cust.data?.total ?? "n/a"}. ARR by region is a bar
        chart; the data has no state-level revenue to map.
      </p>
      {drill && <Drill id={drill} onClose={() => setDrill(null)} />}
    </>
  );
}
