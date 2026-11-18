"use client";

import { Download, Table2, BarChart3 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { saveCsv } from "@/lib/app/format";
import { useUi } from "@/lib/app/store";
import { DEMO, ErrorState } from "./ui";

export const PALETTE = ["#2f74d8", "#00a3a3", "#e69f00", "#8e5bd9", "#d55e5e", "#6c7a89"];

type EChartsOption = Record<string, unknown>;
type Instance = {
  setOption: (o: EChartsOption, notMerge?: boolean) => void;
  resize: () => void;
  dispose: () => void;
  getDataURL: (o: object) => string;
  on: (e: string, f: (p: { name?: string; seriesName?: string; data?: unknown }) => void) => void;
};

export interface ChartTable {
  columns: string[];
  rows: Record<string, unknown>[];
}

/** A chart with a title, an alternative data table, CSV and PNG export, and loading, empty, and error states. */
export function ChartCard({
  title,
  subtitle,
  option,
  table,
  height = 280,
  loading,
  error,
  empty,
  demo,
  filename,
  onPick,
  setup,
}: {
  title: string;
  subtitle?: string;
  option?: EChartsOption;
  table?: ChartTable;
  height?: number;
  loading?: boolean;
  error?: unknown;
  empty?: boolean;
  demo?: boolean;
  filename?: string;
  onPick?: (name: string) => void;
  setup?: (echarts: typeof import("echarts")) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<Instance | null>(null);
  const [asTable, setAsTable] = useState(false);
  const theme = useUi((s) => s.theme);
  const ready = !loading && !error && !empty && option && !asTable;

  useEffect(() => {
    if (!ready || !ref.current) return;
    let disposed = false;
    const el = ref.current;
    import("echarts").then((echarts) => {
      if (disposed) return;
      setup?.(echarts);
      chart.current?.dispose();
      const inst = echarts.init(el, undefined, { renderer: "canvas" }) as unknown as Instance;
      chart.current = inst;
      const text = theme === "dark" ? "#c8d2e4" : "#334155";
      inst.setOption({
        color: PALETTE,
        textStyle: { color: text, fontFamily: "Inter, sans-serif" },
        animationDuration: 200,
        ...option,
      } as EChartsOption);
      if (onPick) inst.on("click", (p) => onPick(String(p.name ?? p.seriesName ?? "")));
    });
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(el);
    return () => {
      disposed = true;
      ro.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
  }, [ready, option, theme, onPick, setup]);

  const exportPng = () => {
    const url = chart.current?.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: theme === "dark" ? "#152038" : "#ffffff",
    });
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filename ?? title}.png`;
    a.click();
  };

  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-ink flex items-center gap-2 text-base font-semibold">
            {title}
            {demo && DEMO}
          </h2>
          {subtitle && <p className="text-sm text-slate-600">{subtitle}</p>}
        </div>
        {table && table.rows.length > 0 && (
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setAsTable((v) => !v)}
              aria-pressed={asTable}
            >
              {asTable ? (
                <BarChart3 className="size-4" aria-hidden />
              ) : (
                <Table2 className="size-4" aria-hidden />
              )}
              {asTable ? "Chart" : "Table"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => saveCsv(`${filename ?? title}.csv`, table.rows, table.columns)}
            >
              <Download className="size-4" aria-hidden />
              CSV
            </Button>
            {!asTable && option && (
              <Button size="sm" variant="ghost" onClick={exportPng}>
                PNG
              </Button>
            )}
          </div>
        )}
      </div>
      {loading ? (
        <Skeleton className="w-full" style={{ height }} />
      ) : error ? (
        <ErrorState error={error} />
      ) : empty || !option ? (
        <div
          className="flex items-center justify-center rounded-[8px] border border-dashed border-slate-300 text-sm text-slate-600"
          style={{ height }}
        >
          No data for this period.
        </div>
      ) : asTable && table ? (
        <div
          key="table"
          className="overflow-auto"
          style={{ maxHeight: height + 40 }}
          tabIndex={0}
          role="region"
          aria-label={`${title}, data table`}
        >
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-line border-b">
                {table.columns.map((c) => (
                  <th key={c} scope="col" className="text-ink px-2 py-1.5 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i} className="border-line border-b">
                  {table.columns.map((c) => (
                    <td key={c} className="px-2 py-1.5 text-slate-700">
                      {String(r[c] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div
          key="chart"
          ref={ref}
          style={{ height }}
          role="img"
          aria-label={`${title}. Use the Table button for the data.`}
        />
      )}
    </Card>
  );
}

/** Shared axis and grid styling so every chart looks the same: light gridlines and units in axis titles. */
export const axis = (name?: string, extra: EChartsOption = {}): EChartsOption => ({
  name,
  nameLocation: "middle",
  nameGap: 42,
  axisLine: { lineStyle: { color: "#94a3b8" } },
  splitLine: { lineStyle: { color: "#e2e8f033" } },
  ...extra,
});
