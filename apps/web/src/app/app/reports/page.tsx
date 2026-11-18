"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { DataTable } from "@/components/app/data-table";
import { PageHeader, Panel } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { api, download } from "@/lib/api";
import { dateTime, label } from "@/lib/app/format";
import { errText, flat, useAction, useCursorList } from "@/lib/app/hooks";
import { useUi } from "@/lib/app/store";
import type { Supplier } from "@/lib/app/types";

interface Report { id: string; kind: string; supplier_id: string | null; status: string; error: string | null; created_at: string; completed_at: string | null; download_url: string | null }

export default function ReportsPage() {
  const toast = useUi((s) => s.toast);
  const [supplier, setSupplier] = useState("");
  const reports = useQuery({ queryKey: ["reports"], queryFn: () => api<{ items: Report[] }>("/reports"), refetchInterval: (q) => (q.state.data?.items.some((r) => r.status === "queued") ? 2000 : false) });
  const sup = useCursorList<Supplier>(["suppliers", "report"], "/suppliers?limit=200");
  const make = useAction((kind: "portfolio" | "supplier") => api(kind === "portfolio" ? "/reports/portfolio" : `/reports/supplier/${supplier}`, { method: "POST" }), { success: "Report requested", invalidate: [["reports"]] });
  return (
    <>
      <PageHeader title="Reports" text="PDF reports with the resolved identity, events with source links, and the score breakdown." />
      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <Panel title="Portfolio report"><p className="mb-3 text-sm text-slate-600">Risk by level, top suppliers, events, and concentration for the whole portfolio.</p><Button onClick={() => make.mutate("portfolio")} disabled={make.isPending}>Create portfolio report</Button></Panel>
        <Panel title="Supplier report">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (supplier) make.mutate("supplier"); }}>
            <Field id="rep-sup" label="Supplier">{(a) => <Select {...a} value={supplier} onChange={(e) => setSupplier(e.target.value)}><option value="">Choose a supplier</option>{flat(sup.data).map((s) => <option key={s.id} value={s.id}>{s.uploaded_name}</option>)}</Select>}</Field>
            <Button type="submit" disabled={!supplier || make.isPending}>Create supplier report</Button>
          </form>
        </Panel>
      </div>
      <DataTable<Report> id="reports" caption="Generated reports" exportName="reports" data={reports.data?.items ?? []} rowKey={(r) => r.id} loading={reports.isLoading} error={reports.error} empty="No reports yet."
        columns={[
          { header: "Kind", accessorFn: (r) => label(r.kind), cell: (c) => <>{label(c.row.original.kind)}{c.row.original.supplier_id && <> (<Link className="text-link underline underline-offset-2" href={`/app/suppliers/${c.row.original.supplier_id}`}>supplier</Link>)</>}</> },
          { header: "Status", accessorKey: "status", cell: (c) => <Badge tone={c.row.original.status === "ready" ? "success" : c.row.original.status === "failed" ? "danger" : "warning"}>{label(c.row.original.status)}</Badge> },
          { header: "Created", accessorKey: "created_at", cell: (c) => dateTime(c.row.original.created_at) },
          { header: "Note", accessorFn: (r) => r.error ?? "" },
          { id: "actions", header: "Download", enableSorting: false, cell: (c) => c.row.original.status === "ready" ? <Button size="sm" variant="secondary" onClick={() => download(`/reports/${c.row.original.id}/download`, `report_${c.row.original.id}.pdf`).catch((e) => toast("error", errText(e)))}>PDF</Button> : null },
        ]} />
    </>
  );
}
