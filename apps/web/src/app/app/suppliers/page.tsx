"use client";

import Link from "next/link";
import { useState } from "react";
import { DataTable } from "@/components/app/data-table";
import { PageHeader, RiskBadge } from "@/components/app/ui";
import { UploadWizard } from "@/components/app/upload-wizard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { api } from "@/lib/api";
import { dateShort, label } from "@/lib/app/format";
import { flat, qs, useAction, useCursorList } from "@/lib/app/hooks";
import { can, useMe } from "@/lib/app/session";
import type { Supplier } from "@/lib/app/types";

interface Filters {
  q: string;
  status: string;
  risk_level: string;
  tier: string;
}
const EMPTY: Filters = { q: "", status: "", risk_level: "", tier: "" };

export default function SuppliersPage() {
  const me = useMe().data;
  const [f, setF] = useState<Filters>(EMPTY);
  const [applied, setApplied] = useState<Filters>(EMPTY);
  const [wizard, setWizard] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [bulkTier, setBulkTier] = useState("tier_1");
  const list = useCursorList<Supplier>(
    ["suppliers", applied],
    `/suppliers${qs({ limit: 50, ...applied })}`,
  );
  const rows = flat(list.data);
  const tag = useAction(
    async () => {
      await Promise.all(
        [...picked].map((id) =>
          api(`/suppliers/${id}`, { method: "PATCH", json: { tier: bulkTier } }),
        ),
      );
    },
    { success: "Tier updated", invalidate: [["suppliers"]], onDone: () => setPicked(new Set()) },
  );
  const operator = can(me, "upload_review");

  const toggle = (id: string) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <>
      <PageHeader
        title="Suppliers"
        text="Every supplier in your portfolio, with its canonical company and latest risk score."
        actions={
          operator ? <Button onClick={() => setWizard(true)}>Upload suppliers</Button> : undefined
        }
      />
      {wizard && (
        <div className="mb-6">
          <UploadWizard onClose={() => setWizard(false)} />
        </div>
      )}
      <form
        className="border-line mb-4 flex flex-wrap items-end gap-3 rounded-[12px] border bg-white p-3"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(f);
        }}
        role="search"
        aria-label="Filter suppliers"
      >
        <div>
          <label htmlFor="f-q" className="mb-1 block text-xs font-medium text-slate-600">
            Search by name
          </label>
          <Input
            id="f-q"
            className="h-9 w-56"
            value={f.q}
            onChange={(e) => setF({ ...f, q: e.target.value })}
          />
        </div>
        <div>
          <label htmlFor="f-status" className="mb-1 block text-xs font-medium text-slate-600">
            Resolution status
          </label>
          <Select
            id="f-status"
            className="h-9"
            value={f.status}
            onChange={(e) => setF({ ...f, status: e.target.value })}
          >
            <option value="">All</option>
            {["auto_resolved", "resolved", "needs_review", "unresolved"].map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="f-risk" className="mb-1 block text-xs font-medium text-slate-600">
            Risk level
          </label>
          <Select
            id="f-risk"
            className="h-9"
            value={f.risk_level}
            onChange={(e) => setF({ ...f, risk_level: e.target.value })}
          >
            <option value="">All</option>
            {["low", "medium", "high", "critical"].map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="f-tier" className="mb-1 block text-xs font-medium text-slate-600">
            Tier
          </label>
          <Select
            id="f-tier"
            className="h-9"
            value={f.tier}
            onChange={(e) => setF({ ...f, tier: e.target.value })}
          >
            <option value="">All</option>
            {["tier_1", "tier_2", "tier_3"].map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </Select>
        </div>
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
      {operator && picked.size > 0 && (
        <div
          className="bg-brand-100 text-ink mb-3 flex flex-wrap items-center gap-2 rounded-[10px] p-3 text-sm"
          role="region"
          aria-label="Bulk actions"
        >
          <span>{picked.size} selected</span>
          <label htmlFor="bulk-tier" className="sr-only">
            Tier to apply
          </label>
          <Select
            id="bulk-tier"
            className="h-9 w-32"
            value={bulkTier}
            onChange={(e) => setBulkTier(e.target.value)}
          >
            {["tier_1", "tier_2", "tier_3"].map((t) => (
              <option key={t} value={t}>
                {label(t)}
              </option>
            ))}
          </Select>
          <Button size="sm" onClick={() => tag.mutate(undefined)} disabled={tag.isPending}>
            Set tier
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>
            Clear selection
          </Button>
        </div>
      )}
      <DataTable<Supplier>
        id="suppliers"
        caption="Suppliers"
        exportName="suppliers"
        data={rows}
        rowKey={(r) => r.id}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        empty="No suppliers match. Upload a supplier list to begin."
        viewState={{ ...applied }}
        onApplyView={(s) => {
          const n = { ...EMPTY, ...(s as Partial<Filters>) };
          setF(n);
          setApplied(n);
        }}
        columns={[
          ...(operator
            ? [
                {
                  id: "select",
                  header: "Select",
                  enableSorting: false,
                  cell: (c: { row: { original: Supplier } }) => (
                    <input
                      type="checkbox"
                      aria-label={`Select ${c.row.original.uploaded_name}`}
                      checked={picked.has(c.row.original.id)}
                      onChange={() => toggle(c.row.original.id)}
                      className="accent-brand-600"
                    />
                  ),
                },
              ]
            : []),
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
            header: "Canonical company",
            accessorFn: (r) => r.company_name ?? "",
            cell: (c) =>
              c.row.original.company_name ?? <span className="text-slate-600">Not linked</span>,
          },
          {
            header: "Status",
            accessorKey: "status",
            cell: (c) => (
              <Badge
                tone={
                  c.row.original.status === "unresolved"
                    ? "danger"
                    : c.row.original.status === "needs_review"
                      ? "warning"
                      : "success"
                }
              >
                {label(c.row.original.status)}
              </Badge>
            ),
          },
          {
            header: "Confidence",
            accessorFn: (r) => r.confidence ?? 0,
            cell: (c) =>
              c.row.original.confidence != null
                ? `${(c.row.original.confidence * 100).toFixed(0)}%`
                : "n/a",
          },
          {
            header: "Risk",
            accessorFn: (r) => Number(r.risk_score ?? -1),
            cell: (c) => (
              <RiskBadge level={c.row.original.risk_level} score={c.row.original.risk_score} />
            ),
          },
          {
            header: "Tier",
            accessorFn: (r) => r.tier ?? "",
            cell: (c) => (c.row.original.tier ? label(c.row.original.tier) : "n/a"),
          },
          {
            header: "Added",
            accessorKey: "created_at",
            cell: (c) => dateShort(c.row.original.created_at),
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
                {list.isFetchingNextPage ? "Loading" : "Load more"}
              </Button>
            </div>
          ) : null
        }
      />
      <p className="mt-4 text-xs text-slate-600">
        Filters by state, industry, and parent company need list fields the API does not return yet.
        Risk signals are leads for human review and not statements of fault.
      </p>
    </>
  );
}
