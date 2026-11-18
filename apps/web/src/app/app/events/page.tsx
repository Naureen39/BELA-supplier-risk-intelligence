"use client";

import Link from "next/link";
import { useState } from "react";
import { DataTable } from "@/components/app/data-table";
import { PageHeader, SeverityBadge } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { dateShort, label, STATES } from "@/lib/app/format";
import { flat, qs, useCursorList } from "@/lib/app/hooks";
import type { EventRow } from "@/lib/app/types";

const SOURCES = ["epa_echo", "osha", "nhtsa", "cpsc", "openfda", "news"];
const TYPES = [
  "workplace_safety",
  "environmental",
  "recall",
  "food_safety",
  "drug_enforcement",
  "plant_incident",
  "bankruptcy",
  "lawsuit",
  "data_breach",
];
interface F {
  source: string;
  event_type: string;
  min_severity: string;
  state: string;
  since: string;
}
const EMPTY: F = { source: "", event_type: "", min_severity: "1", state: "", since: "" };

export default function EventsPage() {
  const [f, setF] = useState<F>(EMPTY);
  const [applied, setApplied] = useState<F>(EMPTY);
  const [group, setGroup] = useState(true);
  const list = useCursorList<EventRow>(
    ["events", applied],
    `/events${qs({ limit: 50, ...applied, since: applied.since ? new Date(applied.since).toISOString() : "" })}`,
  );
  const rows = flat(list.data);
  // Duplicates across sources share a cluster id. Group them under the first (newest) event of the cluster.
  const seen = new Set<number>();
  const shown = group
    ? rows.filter((r) => {
        if (r.cluster_id == null) return true;
        if (seen.has(r.cluster_id)) return false;
        seen.add(r.cluster_id);
        return true;
      })
    : rows;
  const dupes = (r: EventRow) =>
    r.cluster_id == null ? 0 : rows.filter((x) => x.cluster_id === r.cluster_id).length - 1;

  return (
    <>
      <PageHeader
        title="Events"
        text="Regulator records and news events linked to companies in your portfolio, newest first."
      />
      <form
        className="border-line mb-4 flex flex-wrap items-end gap-3 rounded-[12px] border bg-white p-3"
        role="search"
        aria-label="Filter events"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(f);
        }}
      >
        <div>
          <label htmlFor="e-source" className="mb-1 block text-xs font-medium text-slate-600">
            Source
          </label>
          <Select
            id="e-source"
            className="h-9"
            value={f.source}
            onChange={(e) => setF({ ...f, source: e.target.value })}
          >
            <option value="">All</option>
            {SOURCES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="e-type" className="mb-1 block text-xs font-medium text-slate-600">
            Type
          </label>
          <Select
            id="e-type"
            className="h-9"
            value={f.event_type}
            onChange={(e) => setF({ ...f, event_type: e.target.value })}
          >
            <option value="">All</option>
            {TYPES.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="e-sev" className="mb-1 block text-xs font-medium text-slate-600">
            Minimum severity
          </label>
          <Select
            id="e-sev"
            className="h-9"
            value={f.min_severity}
            onChange={(e) => setF({ ...f, min_severity: e.target.value })}
          >
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="e-state" className="mb-1 block text-xs font-medium text-slate-600">
            State
          </label>
          <Select
            id="e-state"
            className="h-9"
            value={f.state}
            onChange={(e) => setF({ ...f, state: e.target.value })}
          >
            <option value="">All</option>
            {Object.keys(STATES).map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="e-since" className="mb-1 block text-xs font-medium text-slate-600">
            Since
          </label>
          <Input
            id="e-since"
            type="date"
            className="h-9 w-40"
            value={f.since}
            onChange={(e) => setF({ ...f, since: e.target.value })}
          />
        </div>
        <label className="text-ink flex h-9 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={group}
            onChange={(e) => setGroup(e.target.checked)}
            className="accent-brand-600 size-4"
          />
          Group duplicates
        </label>
        <Button type="submit" size="sm">
          Apply
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            setF(EMPTY);
            setApplied(EMPTY);
          }}
        >
          Clear
        </Button>
      </form>
      <DataTable<EventRow>
        id="events"
        caption="Events"
        exportName="events"
        data={shown}
        rowKey={(r) => String(r.id)}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        empty="No events match these filters."
        viewState={{ ...applied }}
        onApplyView={(s) => {
          const n = { ...EMPTY, ...(s as Partial<F>) };
          setF(n);
          setApplied(n);
        }}
        columns={[
          {
            header: "Event",
            accessorKey: "title",
            cell: (c) => (
              <Link
                className="text-link font-medium underline underline-offset-2"
                href={`/app/events/${c.row.original.id}`}
              >
                {c.row.original.title}
              </Link>
            ),
          },
          {
            header: "Source",
            accessorKey: "source",
            cell: (c) => <Badge tone="brand">{c.row.original.source}</Badge>,
          },
          { header: "Type", accessorFn: (r) => label(r.event_type) },
          {
            header: "Severity",
            accessorKey: "severity",
            cell: (c) => <SeverityBadge severity={c.row.original.severity} />,
          },
          { header: "State", accessorFn: (r) => r.state ?? "" },
          {
            header: "Reported",
            accessorKey: "reported_at",
            cell: (c) => dateShort(c.row.original.reported_at),
          },
          {
            header: "Duplicates",
            accessorFn: (r) => dupes(r),
            cell: (c) => (dupes(c.row.original) ? `${dupes(c.row.original)} grouped` : ""),
          },
        ]}
        footer={
          list.hasNextPage ? (
            <div className="mt-3 text-center">
              <Button
                variant="secondary"
                onClick={() => void list.fetchNextPage()}
                disabled={list.isFetchingNextPage}
              >
                Load more
              </Button>
            </div>
          ) : null
        }
      />
      <p className="mt-4 text-xs text-slate-600">
        Filtering by linked supplier is available from a supplier profile. Risk signals are leads
        for human review and not statements of fault.
      </p>
    </>
  );
}
