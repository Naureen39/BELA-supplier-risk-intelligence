"use client";

import { Input } from "@/components/ui/field";

export interface Range {
  preset: "30d" | "90d" | "12m" | "all" | "custom";
  from?: string;
  to?: string;
  granularity: "day" | "week" | "month";
  compare: boolean;
}

export const PRESETS: { id: Range["preset"]; label: string }[] = [
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
  { id: "12m", label: "12 months" },
  { id: "all", label: "All time" },
  { id: "custom", label: "Custom" },
];

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Turn a preset into from and to dates, ending at `end` (the latest day of data). */
export function resolveRange(r: Range, end: Date): { from?: string; to?: string } {
  if (r.preset === "custom") return { from: r.from, to: r.to };
  if (r.preset === "all") return {};
  const days = r.preset === "30d" ? 29 : r.preset === "90d" ? 89 : 364;
  return { from: iso(new Date(end.getTime() - days * 86400000)), to: iso(end) };
}

export function RangeBar({
  value,
  onChange,
  granularities = ["day", "week", "month"],
  asOf,
}: {
  value: Range;
  onChange: (r: Range) => void;
  granularities?: Range["granularity"][];
  asOf?: string | null;
}) {
  return (
    <div className="border-line mb-5 flex flex-wrap items-end gap-3 rounded-[12px] border bg-white p-3">
      <fieldset>
        <legend className="mb-1 text-xs font-medium text-slate-600">Period</legend>
        <div className="flex gap-1" role="group" aria-label="Date range presets">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              aria-pressed={value.preset === p.id}
              onClick={() => onChange({ ...value, preset: p.id })}
              className={`h-9 rounded-[8px] border px-3 text-sm font-medium ${value.preset === p.id ? "border-brand-600 bg-brand-600 text-[#ffffff]" : "border-line text-ink bg-white hover:bg-slate-50"}`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </fieldset>
      {value.preset === "custom" && (
        <>
          <div>
            <label htmlFor="rb-from" className="mb-1 block text-xs font-medium text-slate-600">
              From
            </label>
            <Input
              id="rb-from"
              type="date"
              className="h-9 w-40"
              value={value.from ?? ""}
              onChange={(e) => onChange({ ...value, from: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="rb-to" className="mb-1 block text-xs font-medium text-slate-600">
              To
            </label>
            <Input
              id="rb-to"
              type="date"
              className="h-9 w-40"
              value={value.to ?? ""}
              onChange={(e) => onChange({ ...value, to: e.target.value })}
            />
          </div>
        </>
      )}
      <div>
        <label htmlFor="rb-gran" className="mb-1 block text-xs font-medium text-slate-600">
          Granularity
        </label>
        <select
          id="rb-gran"
          value={value.granularity}
          onChange={(e) =>
            onChange({ ...value, granularity: e.target.value as Range["granularity"] })
          }
          className="text-ink h-9 rounded-[8px] border border-slate-300 bg-white px-2 text-sm"
        >
          {granularities.map((g) => (
            <option key={g} value={g}>
              {g[0]?.toUpperCase()}
              {g.slice(1)}
            </option>
          ))}
        </select>
      </div>
      <label className="text-ink flex h-9 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={value.compare}
          onChange={(e) => onChange({ ...value, compare: e.target.checked })}
          className="accent-brand-600 size-4"
        />
        Compare with the previous period
      </label>
      {asOf && <p className="ml-auto text-xs text-slate-600">As of {asOf}</p>}
    </div>
  );
}
