"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/app/data-table";
import { ErrorState, PageHeader, Panel, SkeletonRows } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { dateTime, label, num } from "@/lib/app/format";

interface Sources {
  counts: Record<string, number>;
  event_sources: { source: string; records: number; latest: string }[];
  licenses: Record<string, string>;
  coverage_note: string;
}
interface Quality {
  data_freshness: {
    source: string;
    records: number;
    latest_record_at: string;
    age_days: number;
    status: string;
    fresh_within_days: number;
  }[];
}

export default function SourcesPage() {
  const s = useQuery({ queryKey: ["sources"], queryFn: () => api<Sources>("/sources") });
  const f = useQuery({
    queryKey: ["sources-fresh"],
    queryFn: () => api<Quality>("/analytics/quality?granularity=month"),
  });
  if (s.isLoading) return <SkeletonRows rows={6} />;
  if (s.error || !s.data) return <ErrorState error={s.error} retry={() => void s.refetch()} />;
  const d = s.data;
  const fresh = new Map((f.data?.data_freshness ?? []).map((x) => [x.source, x]));
  return (
    <>
      <PageHeader
        title="Data sources"
        text="What the platform has loaded, how current it is, and the terms each source comes with."
      />
      <Panel className="mb-6">
        <p className="text-ink text-sm">{d.coverage_note}</p>
      </Panel>
      <section aria-label="Record counts" className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-5">
        {Object.entries(d.counts).map(([k, v]) => (
          <Panel key={k}>
            <p className="text-xs text-slate-600">{label(k)}</p>
            <p className="text-ink text-2xl font-semibold">{num(v)}</p>
          </Panel>
        ))}
      </section>
      <h2 className="text-ink mb-3 text-base font-semibold">Event sources</h2>
      <DataTable<Sources["event_sources"][number]>
        id="event-sources"
        caption="Event sources with freshness"
        exportName="event-sources"
        data={d.event_sources}
        rowKey={(r) => r.source}
        empty="No events have been loaded."
        columns={[
          { header: "Source", accessorKey: "source" },
          { header: "Records", accessorKey: "records" },
          {
            header: "Latest record",
            accessorKey: "latest",
            cell: (c) => dateTime(c.row.original.latest),
          },
          {
            header: "Freshness",
            accessorFn: (r) => fresh.get(r.source)?.status ?? "n/a",
            cell: (c) => {
              const x = fresh.get(c.row.original.source);
              return x ? (
                <Badge
                  tone={
                    x.status === "fresh" ? "success" : x.status === "aging" ? "warning" : "danger"
                  }
                >
                  {label(x.status)}
                </Badge>
              ) : (
                "n/a"
              );
            },
          },
          { header: "License note", accessorFn: (r) => d.licenses[r.source] ?? "" },
        ]}
      />
      <p className="mt-3 text-xs text-slate-600">
        Freshness compares the latest record date with a configured threshold (2 days for news, 10
        days otherwise). It reports the newest record, not the last successful run, because no run
        log exists yet.
      </p>
      <h2 className="text-ink mt-8 mb-3 text-base font-semibold">Licenses and terms</h2>
      <dl className="grid gap-3 sm:grid-cols-2">
        {Object.entries(d.licenses).map(([k, v]) => (
          <div key={k} className="border-line rounded-[10px] border bg-white p-3">
            <dt className="text-ink text-sm font-medium">{k}</dt>
            <dd className="text-sm text-slate-600">{v}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}
