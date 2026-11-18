"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { DataTable } from "@/components/app/data-table";
import { ConfirmDialog, PageHeader, Panel } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { ago, dateTime, label } from "@/lib/app/format";
import { flat, qs, useAction, useCursorList } from "@/lib/app/hooks";
import { can, useMe } from "@/lib/app/session";
import type { AlertRow } from "@/lib/app/types";

const STATUSES = ["new", "in_review", "acknowledged", "escalated", "dismissed"];
const TONE: Record<string, "warning" | "brand" | "success" | "danger" | "neutral"> = {
  new: "warning",
  in_review: "brand",
  acknowledged: "success",
  escalated: "danger",
  dismissed: "neutral",
};
interface Hist {
  id: number;
  actor_user_id: string | null;
  change: string;
  reason: string | null;
  comment: string | null;
  occurred_at: string;
}
interface UserLite {
  id: string;
  email: string;
  role: string;
}
interface Rule {
  id: string;
  name: string;
  event_types: string[];
  min_severity: number;
  supplier_tiers: string[];
  states: string[];
  channels: string[];
  webhook_url: string | null;
  is_active: boolean;
}

function Detail({
  alert,
  onClose,
  canAct,
  users,
}: {
  alert: AlertRow;
  onClose: () => void;
  canAct: boolean;
  users: UserLite[];
}) {
  const hist = useQuery({
    queryKey: ["alert-history", alert.id],
    queryFn: () => api<{ items: Hist[] }>(`/alerts/${alert.id}/history`),
  });
  const [comment, setComment] = useState("");
  const [dismiss, setDismiss] = useState(false);
  const [reason, setReason] = useState("");
  const inv = [["alerts"], ["alert-history", alert.id], ["overview"]];
  const patch = useAction(
    (body: Record<string, unknown>) => api(`/alerts/${alert.id}`, { method: "PATCH", json: body }),
    { success: "Alert updated", invalidate: inv },
  );
  const post = useAction(() => api(`/alerts/${alert.id}/comments`, { json: { comment } }), {
    success: "Comment added",
    invalidate: inv,
    onDone: () => setComment(""),
  });
  return (
    <Dialog.Root open onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(96vw,460px)] flex-col gap-4 overflow-y-auto bg-white p-6 shadow-[var(--shadow-3)]">
          <Dialog.Title className="text-ink text-lg font-semibold">
            {alert.supplier_name}
          </Dialog.Title>
          <Dialog.Description className="text-sm text-slate-600">
            {alert.detail ?? label(alert.kind)}. Raised {dateTime(alert.created_at)}.
          </Dialog.Description>
          <div className="flex items-center gap-2">
            <Badge tone={TONE[alert.status] ?? "neutral"}>{label(alert.status)}</Badge>
            <Link
              href={`/app/suppliers/${alert.supplier_id}`}
              className="text-link text-sm underline underline-offset-2"
            >
              Open supplier
            </Link>
          </div>
          {canAct && (
            <>
              <div className="flex flex-wrap gap-2">
                {STATUSES.filter((s) => s !== alert.status && s !== "dismissed").map((s) => (
                  <Button
                    key={s}
                    size="sm"
                    variant="secondary"
                    onClick={() => patch.mutate({ status: s })}
                  >
                    {label(s)}
                  </Button>
                ))}
                {alert.status !== "dismissed" && (
                  <Button size="sm" variant="destructive" onClick={() => setDismiss(true)}>
                    Dismiss
                  </Button>
                )}
              </div>
              <Field id="assignee" label="Assignee">
                {(a) => (
                  <Select
                    {...a}
                    value={alert.assignee_id ?? ""}
                    onChange={(e) => patch.mutate({ assignee_id: e.target.value })}
                  >
                    <option value="" disabled>
                      Unassigned
                    </option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.email}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  post.mutate(undefined);
                }}
                className="space-y-2"
              >
                <Field id="comment" label="Add a comment">
                  {(a) => (
                    <Textarea
                      {...a}
                      value={comment}
                      maxLength={2000}
                      onChange={(e) => setComment(e.target.value)}
                    />
                  )}
                </Field>
                <Button type="submit" size="sm" disabled={!comment.trim() || post.isPending}>
                  Comment
                </Button>
              </form>
            </>
          )}
          <section aria-label="History">
            <h3 className="text-ink mb-2 text-sm font-semibold">History</h3>
            <ol className="space-y-2 text-sm">
              {(hist.data?.items ?? []).map((h) => (
                <li key={h.id} className="rounded-[8px] bg-slate-50 p-2">
                  <span className="text-ink font-medium">{label(h.change)}</span>
                  {h.reason && <> (reason: {h.reason})</>}
                  {h.comment && <>: {h.comment}</>}
                  <span className="block text-xs text-slate-600">{dateTime(h.occurred_at)}</span>
                </li>
              ))}
              {hist.data?.items.length === 0 && <li className="text-slate-600">No changes yet.</li>}
            </ol>
          </section>
          <Dialog.Close asChild>
            <Button variant="secondary" className="mt-auto">
              Close
            </Button>
          </Dialog.Close>
          <ConfirmDialog
            open={dismiss}
            onOpenChange={setDismiss}
            title="Dismiss this alert"
            text="A reason is required and is recorded in the alert history."
            confirmLabel="Dismiss alert"
            destructive
            onConfirm={() => reason.trim() && patch.mutate({ status: "dismissed", reason })}
          >
            <div className="mt-4">
              <label htmlFor="dismiss-reason" className="text-ink mb-1 block text-sm font-medium">
                Reason
              </label>
              <Textarea
                id="dismiss-reason"
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
          </ConfirmDialog>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Rules() {
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => api<{ items: Rule[] }>("/rules") });
  const [edit, setEdit] = useState<Partial<Rule> | null>(null);
  const save = useAction(
    (r: Partial<Rule>) =>
      r.id
        ? api(`/rules/${r.id}`, {
            method: "PATCH",
            json: {
              name: r.name,
              min_severity: r.min_severity,
              event_types: r.event_types,
              supplier_tiers: r.supplier_tiers,
              states: r.states,
              channels: r.channels,
              webhook_url: r.webhook_url,
              is_active: r.is_active,
            },
          })
        : api("/rules", { json: r }),
    { success: "Rule saved", invalidate: [["rules"]], onDone: () => setEdit(null) },
  );
  const toggle = useAction(
    (r: Rule) => api(`/rules/${r.id}`, { method: "PATCH", json: { is_active: !r.is_active } }),
    { invalidate: [["rules"]] },
  );
  const csv = (s: string) =>
    s
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
  return (
    <Panel
      title="Alert rules"
      actions={
        <Button
          size="sm"
          onClick={() =>
            setEdit({
              name: "",
              min_severity: 3,
              event_types: [],
              supplier_tiers: [],
              states: [],
              channels: ["in_app"],
              is_active: true,
            })
          }
        >
          New rule
        </Button>
      }
    >
      <DataTable<Rule>
        id="rules"
        caption="Alert rules"
        data={rules.data?.items ?? []}
        rowKey={(r) => r.id}
        loading={rules.isLoading}
        error={rules.error}
        empty="No rules yet. Without a rule, high-severity events still raise in-app alerts."
        columns={[
          { header: "Name", accessorKey: "name" },
          { header: "Min severity", accessorKey: "min_severity" },
          { header: "Event types", accessorFn: (r) => r.event_types.join(", ") || "All" },
          { header: "Tiers", accessorFn: (r) => r.supplier_tiers.join(", ") || "All" },
          { header: "States", accessorFn: (r) => r.states.join(", ") || "All" },
          { header: "Channels", accessorFn: (r) => r.channels.join(", ") },
          {
            id: "actions",
            header: "Actions",
            enableSorting: false,
            cell: (c) => (
              <span className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => setEdit(c.row.original)}>
                  Edit
                </Button>
                <Button size="sm" variant="ghost" onClick={() => toggle.mutate(c.row.original)}>
                  {c.row.original.is_active ? "Turn off" : "Turn on"}
                </Button>
              </span>
            ),
          },
        ]}
      />
      {edit && (
        <Dialog.Root open onOpenChange={(v) => !v && setEdit(null)}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
            <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[90vh] w-[min(94vw,520px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[12px] bg-white p-6 shadow-[var(--shadow-3)]">
              <Dialog.Title className="text-ink text-lg font-semibold">
                {edit.id ? "Edit rule" : "New rule"}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-slate-600">
                Leave a list empty to match everything.
              </Dialog.Description>
              <form
                className="mt-4 space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  save.mutate(edit);
                }}
              >
                <Field id="r-name" label="Name">
                  {(a) => (
                    <Input
                      {...a}
                      required
                      value={edit.name ?? ""}
                      onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                    />
                  )}
                </Field>
                <Field id="r-sev" label="Minimum severity (1 to 4)">
                  {(a) => (
                    <Select
                      {...a}
                      value={edit.min_severity ?? 3}
                      onChange={(e) => setEdit({ ...edit, min_severity: Number(e.target.value) })}
                    >
                      {[1, 2, 3, 4].map((n) => (
                        <option key={n}>{n}</option>
                      ))}
                    </Select>
                  )}
                </Field>
                <Field
                  id="r-types"
                  label="Event types"
                  hint="Comma separated, for example recall, workplace_safety"
                >
                  {(a) => (
                    <Input
                      {...a}
                      value={(edit.event_types ?? []).join(", ")}
                      onChange={(e) => setEdit({ ...edit, event_types: csv(e.target.value) })}
                    />
                  )}
                </Field>
                <Field id="r-tiers" label="Supplier tiers" hint="For example tier_1, tier_2">
                  {(a) => (
                    <Input
                      {...a}
                      value={(edit.supplier_tiers ?? []).join(", ")}
                      onChange={(e) => setEdit({ ...edit, supplier_tiers: csv(e.target.value) })}
                    />
                  )}
                </Field>
                <Field id="r-states" label="States" hint="Two-letter codes, for example OH, TX">
                  {(a) => (
                    <Input
                      {...a}
                      value={(edit.states ?? []).join(", ")}
                      onChange={(e) => setEdit({ ...edit, states: csv(e.target.value) })}
                    />
                  )}
                </Field>
                <fieldset>
                  <legend className="text-ink mb-1 text-sm font-medium">Notify by</legend>
                  {["in_app", "email", "webhook"].map((c) => (
                    <label key={c} className="text-ink mr-4 inline-flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={(edit.channels ?? []).includes(c)}
                        onChange={(e) =>
                          setEdit({
                            ...edit,
                            channels: e.target.checked
                              ? [...(edit.channels ?? []), c]
                              : (edit.channels ?? []).filter((x) => x !== c),
                          })
                        }
                      />
                      {label(c)}
                    </label>
                  ))}
                </fieldset>
                {(edit.channels ?? []).includes("webhook") && (
                  <Field id="r-hook" label="Webhook URL (https)">
                    {(a) => (
                      <Input
                        {...a}
                        type="url"
                        required
                        value={edit.webhook_url ?? ""}
                        onChange={(e) => setEdit({ ...edit, webhook_url: e.target.value })}
                      />
                    )}
                  </Field>
                )}
                <div className="flex justify-end gap-2">
                  <Dialog.Close asChild>
                    <Button type="button" variant="secondary">
                      Cancel
                    </Button>
                  </Dialog.Close>
                  <Button type="submit" disabled={save.isPending}>
                    Save rule
                  </Button>
                </div>
              </form>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </Panel>
  );
}

export default function AlertsPage() {
  const me = useMe().data;
  const [status, setStatus] = useState("");
  const [assignee, setAssignee] = useState("");
  const [open, setOpen] = useState<AlertRow | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const list = useCursorList<AlertRow>(
    ["alerts", status, assignee],
    `/alerts${qs({ limit: 50, status, assignee })}`,
  );
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<{ items: UserLite[] }>("/users"),
  });
  const rows = flat(list.data);
  const canAct = can(me, "alert_action");
  const bulk = useAction(
    async (s: string) => {
      await Promise.all(
        [...picked].map((id) =>
          api(`/alerts/${id}`, { method: "PATCH", json: { status: s } }).catch(() => undefined),
        ),
      );
    },
    { success: "Alerts updated", invalidate: [["alerts"]], onDone: () => setPicked(new Set()) },
  );

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (
        (e.target as HTMLElement).closest("input, textarea, select, [role=dialog]") ||
        e.ctrlKey ||
        e.metaKey
      )
        return;
      const i = open ? rows.findIndex((r) => r.id === open.id) : -1;
      if (e.key === "j" && rows[i + 1]) setOpen(rows[i + 1]!);
      if (e.key === "k" && rows[i - 1]) setOpen(rows[i - 1]!);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [rows, open]);

  const queue = (
    <>
      <form
        className="border-line mb-4 flex flex-wrap items-end gap-3 rounded-[12px] border bg-white p-3"
        role="search"
        aria-label="Filter alerts"
        onSubmit={(e) => e.preventDefault()}
      >
        <div>
          <label htmlFor="a-status" className="mb-1 block text-xs font-medium text-slate-600">
            Status
          </label>
          <Select
            id="a-status"
            className="h-9"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="a-assignee" className="mb-1 block text-xs font-medium text-slate-600">
            Assignee
          </label>
          <Select
            id="a-assignee"
            className="h-9"
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
          >
            <option value="">Anyone</option>
            {(users.data?.items ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.email}
              </option>
            ))}
          </Select>
        </div>
        {canAct && picked.size > 0 && (
          <div className="ml-auto flex items-center gap-2 text-sm">
            <span>{picked.size} selected</span>
            <Button size="sm" variant="secondary" onClick={() => bulk.mutate("acknowledged")}>
              Acknowledge
            </Button>
            <Button size="sm" variant="secondary" onClick={() => bulk.mutate("in_review")}>
              Mark in review
            </Button>
          </div>
        )}
      </form>
      <DataTable<AlertRow>
        id="alerts"
        caption="Alerts"
        exportName="alerts"
        data={rows}
        rowKey={(r) => r.id}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        empty="No alerts match these filters."
        onRowClick={setOpen}
        columns={[
          ...(canAct
            ? [
                {
                  id: "select",
                  header: "Select",
                  enableSorting: false,
                  cell: (c: { row: { original: AlertRow } }) => (
                    <input
                      type="checkbox"
                      aria-label={`Select alert for ${c.row.original.supplier_name}`}
                      checked={picked.has(c.row.original.id)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() =>
                        setPicked((s) => {
                          const n = new Set(s);
                          if (n.has(c.row.original.id)) n.delete(c.row.original.id);
                          else n.add(c.row.original.id);
                          return n;
                        })
                      }
                      className="accent-brand-600"
                    />
                  ),
                },
              ]
            : []),
          {
            header: "Supplier",
            accessorKey: "supplier_name",
            cell: (c) => (
              <button
                type="button"
                className="text-link font-medium underline underline-offset-2"
                onClick={(e) => {
                  e.stopPropagation();
                  setOpen(c.row.original);
                }}
              >
                {c.row.original.supplier_name}
              </button>
            ),
          },
          { header: "Detail", accessorFn: (r) => r.detail ?? label(r.kind) },
          {
            header: "Status",
            accessorKey: "status",
            cell: (c) => (
              <Badge tone={TONE[c.row.original.status] ?? "neutral"}>
                {label(c.row.original.status)}
              </Badge>
            ),
          },
          {
            header: "Assignee",
            accessorFn: (r) =>
              users.data?.items.find((u) => u.id === r.assignee_id)?.email ?? "Unassigned",
          },
          {
            header: "Raised",
            accessorKey: "created_at",
            cell: (c) => ago(c.row.original.created_at),
          },
        ]}
        footer={
          list.hasNextPage ? (
            <div className="mt-3 text-center">
              <Button variant="secondary" onClick={() => void list.fetchNextPage()}>
                Load more
              </Button>
            </div>
          ) : null
        }
      />
      <p className="mt-3 text-xs text-slate-600">
        Keyboard: J and K open the next or previous alert. Alerts are leads for human review and not
        statements of fault.
      </p>
      {open && (
        <Detail
          alert={rows.find((r) => r.id === open.id) ?? open}
          onClose={() => setOpen(null)}
          canAct={canAct}
          users={users.data?.items ?? []}
        />
      )}
    </>
  );

  return (
    <>
      <PageHeader
        title="Alerts"
        text="Work the queue: acknowledge, assign, comment, or dismiss with a reason."
      />
      {can(me, "manage_rules") ? (
        <Tabs
          label="Alert sections"
          items={[
            { id: "queue", label: "Queue", content: queue },
            { id: "rules", label: "Rules", content: <Rules /> },
          ]}
        />
      ) : (
        queue
      )}
    </>
  );
}
