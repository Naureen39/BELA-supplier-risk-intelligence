"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/app/data-table";
import { ErrorState, PageHeader, Panel, SkeletonRows } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { dateShort, label, num, usd } from "@/lib/app/format";
import { PRICING } from "@/lib/site";

interface Plan {
  demo_data: boolean;
  plan: {
    plan_code: string;
    name: string;
    billing_cycle: string;
    price: number;
    started_on: string;
    supplier_limit: number;
    overage_per_100: number;
  } | null;
  monitored_suppliers: number;
}
interface Inv {
  id: number;
  period_month: string;
  issued_on: string;
  due_on: string;
  status: string;
  total: number;
}

export default function BillingPage() {
  const plan = useQuery({ queryKey: ["billing-plan"], queryFn: () => api<Plan>("/billing/plan") });
  const inv = useQuery({
    queryKey: ["billing-invoices"],
    queryFn: () => api<{ items: Inv[] }>("/billing/invoices"),
  });
  if (plan.isLoading) return <SkeletonRows rows={5} />;
  if (plan.error || !plan.data)
    return <ErrorState error={plan.error} retry={() => void plan.refetch()} />;
  const p = plan.data;
  const used = p.monitored_suppliers;
  const limit = p.plan?.supplier_limit ?? 0;
  const ratio = limit ? Math.min(100, (100 * used) / limit) : 0;
  return (
    <>
      <PageHeader
        title="Billing"
        text="Your plan, supplier usage against the limit, and invoices. No payment is collected in this demonstration."
        demo
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Current plan">
          {p.plan ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs text-slate-600">Plan</dt>
                <dd className="text-ink font-medium">{p.plan.name ?? label(p.plan.plan_code)}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-600">Billing</dt>
                <dd className="text-ink">
                  {label(p.plan.billing_cycle)}, {usd(p.plan.price)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-600">Started</dt>
                <dd className="text-ink">{dateShort(p.plan.started_on)}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-600">Overage</dt>
                <dd className="text-ink">{usd(p.plan.overage_per_100)} per 100 suppliers</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-slate-600">No subscription is recorded for this tenant.</p>
          )}
        </Panel>
        <Panel title="Monitored suppliers versus limit">
          <div
            role="meter"
            aria-valuemin={0}
            aria-valuemax={limit || 1}
            aria-valuenow={used}
            aria-label="Monitored suppliers versus the plan limit"
            className="h-4 w-full overflow-hidden rounded-full bg-slate-100"
          >
            <div
              className={`h-4 ${ratio >= 100 ? "bg-danger" : ratio >= 80 ? "bg-warning" : "bg-chart-2"}`}
              style={{ width: `${ratio}%` }}
            />
          </div>
          <p className="text-ink mt-2 text-sm">
            {num(used)} of {limit ? num(limit) : "n/a"} suppliers
            {limit && used > limit ? (
              <Badge tone="warning" className="ml-2">
                Over the limit
              </Badge>
            ) : null}
          </p>
        </Panel>
      </div>
      <h2 className="text-ink mt-8 mb-3 text-base font-semibold">Invoices</h2>
      <DataTable<Inv>
        id="invoices"
        caption="Invoices"
        exportName="invoices"
        data={inv.data?.items ?? []}
        rowKey={(i) => String(i.id)}
        loading={inv.isLoading}
        error={inv.error}
        empty="No invoices."
        columns={[
          {
            header: "Period",
            accessorKey: "period_month",
            cell: (c) => dateShort(c.row.original.period_month),
          },
          {
            header: "Issued",
            accessorKey: "issued_on",
            cell: (c) => dateShort(c.row.original.issued_on),
          },
          { header: "Due", accessorKey: "due_on", cell: (c) => dateShort(c.row.original.due_on) },
          { header: "Total", accessorKey: "total", cell: (c) => usd(c.row.original.total, 2) },
          {
            header: "Status",
            accessorKey: "status",
            cell: (c) => (
              <Badge
                tone={
                  c.row.original.status === "paid"
                    ? "success"
                    : c.row.original.status === "overdue"
                      ? "danger"
                      : "neutral"
                }
              >
                {label(c.row.original.status)}
              </Badge>
            ),
          },
        ]}
      />
      <p className="mt-2 text-xs text-slate-600">
        Invoice PDF download is not available yet; the invoice list can be exported as CSV.
      </p>
      <h2 className="text-ink mt-8 mb-3 text-base font-semibold">Plans</h2>
      <p className="mb-3 text-xs text-slate-600">{PRICING.label}</p>
      <div className="grid gap-4 md:grid-cols-3">
        {PRICING.plans.map((pl) => (
          <Panel key={pl.code} title={pl.name}>
            <p className="text-ink text-xl font-semibold">
              ${pl.price} <span className="text-sm font-normal text-slate-600">{pl.unit}</span>
            </p>
            <ul className="mt-2 list-disc pl-5 text-sm text-slate-700">
              {pl.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            {p.plan?.plan_code === pl.code && (
              <Badge tone="brand" className="mt-3">
                Current plan
              </Badge>
            )}
          </Panel>
        ))}
      </div>
    </>
  );
}
