"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { DataTable } from "@/components/app/data-table";
import { ConfirmDialog, PageHeader, Panel } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { dateTime, label, saveCsv } from "@/lib/app/format";
import { errText, flat, qs, useAction, useCursorList } from "@/lib/app/hooks";
import { can, useMe } from "@/lib/app/session";
import { useUi } from "@/lib/app/store";

interface User {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}
interface Key {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}
interface Audit {
  seq: number;
  occurred_at: string;
  actor_user_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown>;
}
interface RC {
  version: number;
  config: Record<string, unknown>;
}
interface Tenant {
  name: string;
  require_mfa: boolean;
  retention_days: number;
  share_feedback_for_training: boolean;
}
const ROLES = ["viewer", "analyst", "manager", "tenant_admin"];
const SCOPES = ["view", "upload_review", "alert_action", "manage_rules"];

function Users() {
  const list = useCursorList<User>(["admin-users"], "/admin/users?limit=100");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("viewer");
  const invite = useAction(() => api("/admin/users", { json: { email, role } }), {
    success: "Invitation sent",
    invalidate: [["admin-users"]],
    onDone: () => setEmail(""),
  });
  const patch = useAction(
    (v: { id: string; body: Record<string, unknown> }) =>
      api(`/admin/users/${v.id}`, { method: "PATCH", json: v.body }),
    { success: "User updated", invalidate: [["admin-users"]] },
  );
  const [off, setOff] = useState<User | null>(null);
  return (
    <div className="space-y-6">
      <Panel title="Invite a user">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            invite.mutate(undefined);
          }}
        >
          <Field id="inv-email" label="Email">
            {(a) => (
              <Input
                {...a}
                type="email"
                required
                className="w-64"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <Field id="inv-role" label="Role">
            {(a) => (
              <Select {...a} value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {label(r)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Button type="submit" disabled={invite.isPending}>
            Send invitation
          </Button>
        </form>
      </Panel>
      <DataTable<User>
        id="users"
        caption="Users"
        exportName="users"
        data={flat(list.data)}
        rowKey={(u) => u.id}
        loading={list.isLoading}
        error={list.error}
        columns={[
          { header: "Email", accessorKey: "email" },
          {
            header: "Role",
            accessorKey: "role",
            cell: (c) => (
              <>
                <label className="sr-only" htmlFor={`role-${c.row.original.id}`}>
                  Role for {c.row.original.email}
                </label>
                <Select
                  id={`role-${c.row.original.id}`}
                  className="h-9 w-40"
                  value={c.row.original.role}
                  onChange={(e) =>
                    patch.mutate({ id: c.row.original.id, body: { role: e.target.value } })
                  }
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {label(r)}
                    </option>
                  ))}
                </Select>
              </>
            ),
          },
          {
            header: "Status",
            accessorFn: (u) => (u.is_active ? "Active" : "Disabled"),
            cell: (c) => (
              <Badge tone={c.row.original.is_active ? "success" : "neutral"}>
                {c.row.original.is_active ? "Active" : "Disabled"}
              </Badge>
            ),
          },
          {
            header: "Last sign-in",
            accessorFn: (u) => u.last_login_at ?? "",
            cell: (c) => dateTime(c.row.original.last_login_at),
          },
          {
            id: "actions",
            header: "Actions",
            enableSorting: false,
            cell: (c) =>
              c.row.original.is_active ? (
                <Button size="sm" variant="ghost" onClick={() => setOff(c.row.original)}>
                  Disable
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => patch.mutate({ id: c.row.original.id, body: { is_active: true } })}
                >
                  Enable
                </Button>
              ),
          },
        ]}
      />
      <ConfirmDialog
        open={!!off}
        onOpenChange={(v) => !v && setOff(null)}
        title="Disable this user"
        text={`${off?.email} will no longer be able to sign in, and their sessions end.`}
        confirmLabel="Disable user"
        destructive
        onConfirm={() => off && patch.mutate({ id: off.id, body: { is_active: false } })}
      />
    </div>
  );
}

function Keys() {
  const keys = useQuery({
    queryKey: ["keys"],
    queryFn: () => api<{ items: Key[] }>("/admin/api-keys"),
  });
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["view"]);
  const [days, setDays] = useState("90");
  const [shown, setShown] = useState<string | null>(null);
  const [revoke, setRevoke] = useState<Key | null>(null);
  const create = useAction(
    () =>
      api<{ key: string }>("/admin/api-keys", {
        json: { name, scopes, expires_in_days: Number(days) },
      }),
    {
      invalidate: [["keys"]],
      onDone: (r) => {
        setShown(r.key);
        setName("");
      },
    },
  );
  const rev = useAction((id: string) => api(`/admin/api-keys/${id}`, { method: "DELETE" }), {
    success: "Key revoked",
    invalidate: [["keys"]],
  });
  return (
    <div className="space-y-6">
      <Panel title="Create an API key">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(undefined);
          }}
        >
          <div className="flex flex-wrap items-end gap-3">
            <Field id="k-name" label="Name">
              {(a) => (
                <Input
                  {...a}
                  required
                  maxLength={80}
                  className="w-56"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              )}
            </Field>
            <Field id="k-days" label="Expires in (days)">
              {(a) => (
                <Input
                  {...a}
                  type="number"
                  min={1}
                  max={730}
                  className="w-32"
                  value={days}
                  onChange={(e) => setDays(e.target.value)}
                />
              )}
            </Field>
          </div>
          <fieldset>
            <legend className="text-ink mb-1 text-sm font-medium">Scopes</legend>
            {SCOPES.map((s) => (
              <label key={s} className="text-ink mr-4 inline-flex items-center gap-2 text-sm">
                <Checkbox
                  checked={scopes.includes(s)}
                  onChange={(e) =>
                    setScopes(e.target.checked ? [...scopes, s] : scopes.filter((x) => x !== s))
                  }
                />
                {label(s)}
              </label>
            ))}
          </fieldset>
          <Button type="submit" disabled={!scopes.length || create.isPending}>
            Create key
          </Button>
        </form>
        {shown && (
          <div role="alert" className="border-warning mt-4 rounded-[10px] border bg-white p-3">
            <p className="text-ink text-sm font-medium">
              Copy this key now. It cannot be shown again.
            </p>
            <p className="text-ink mt-1 font-mono text-sm break-all">{shown}</p>
            <Button size="sm" variant="secondary" className="mt-2" onClick={() => setShown(null)}>
              I have stored it
            </Button>
          </div>
        )}
      </Panel>
      <DataTable<Key>
        id="keys"
        caption="API keys"
        exportName="api-keys"
        data={keys.data?.items ?? []}
        rowKey={(k) => k.id}
        loading={keys.isLoading}
        error={keys.error}
        empty="No API keys."
        columns={[
          { header: "Name", accessorKey: "name" },
          { header: "Prefix", accessorKey: "prefix" },
          { header: "Scopes", accessorFn: (k) => k.scopes.join(", ") },
          {
            header: "Expires",
            accessorFn: (k) => k.expires_at ?? "",
            cell: (c) => dateTime(c.row.original.expires_at),
          },
          {
            header: "Last used",
            accessorFn: (k) => k.last_used_at ?? "",
            cell: (c) => dateTime(c.row.original.last_used_at),
          },
          {
            header: "Status",
            accessorFn: (k) => (k.revoked_at ? "Revoked" : "Active"),
            cell: (c) => (
              <Badge tone={c.row.original.revoked_at ? "neutral" : "success"}>
                {c.row.original.revoked_at ? "Revoked" : "Active"}
              </Badge>
            ),
          },
          {
            id: "actions",
            header: "Actions",
            enableSorting: false,
            cell: (c) =>
              !c.row.original.revoked_at ? (
                <Button size="sm" variant="ghost" onClick={() => setRevoke(c.row.original)}>
                  Revoke
                </Button>
              ) : null,
          },
        ]}
      />
      <ConfirmDialog
        open={!!revoke}
        onOpenChange={(v) => !v && setRevoke(null)}
        title="Revoke this key"
        text={`Anything using "${revoke?.name}" stops working immediately.`}
        confirmLabel="Revoke key"
        destructive
        onConfirm={() => revoke && rev.mutate(revoke.id)}
      />
    </div>
  );
}

function AuditLog() {
  const toast = useUi((s) => s.toast);
  const [action, setAction] = useState("");
  const list = useCursorList<Audit>(["audit", action], `/admin/audit${qs({ limit: 100, action })}`);
  const verify = useQuery({
    queryKey: ["audit-verify"],
    queryFn: () =>
      api<{ ok: boolean; rows_checked: number; first_bad_seq: number | null }>(
        "/admin/audit/verify",
      ),
    staleTime: 0,
  });
  const rows = flat(list.data);
  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-end gap-3">
          <Field id="aud-action" label="Action">
            {(a) => (
              <Input
                {...a}
                placeholder="for example user.created"
                className="w-64"
                value={action}
                onChange={(e) => setAction(e.target.value)}
              />
            )}
          </Field>
          <Button
            variant="secondary"
            onClick={() =>
              saveCsv(
                "audit-log.csv",
                rows.map((r) => ({
                  seq: r.seq,
                  at: r.occurred_at,
                  actor: r.actor_user_id,
                  action: r.action,
                  target_type: r.target_type,
                  target_id: r.target_id,
                  detail: JSON.stringify(r.detail),
                })),
              )
            }
            disabled={!rows.length}
          >
            Export CSV
          </Button>
          <Button
            variant="ghost"
            onClick={() =>
              void verify
                .refetch()
                .then((r) =>
                  toast(
                    r.data?.ok ? "success" : "error",
                    r.data?.ok
                      ? `Chain verified: ${r.data.rows_checked} entries.`
                      : `Chain broken at entry ${r.data?.first_bad_seq}.`,
                  ),
                )
                .catch((e) => toast("error", errText(e)))
            }
          >
            Verify the hash chain
          </Button>
          {verify.data && (
            <Badge tone={verify.data.ok ? "success" : "danger"}>
              {verify.data.ok
                ? `Chain intact (${verify.data.rows_checked} entries)`
                : "Chain broken"}
            </Badge>
          )}
        </div>
      </Panel>
      <DataTable<Audit>
        id="audit"
        caption="Audit log"
        exportName="audit"
        data={rows}
        rowKey={(r) => String(r.seq)}
        loading={list.isLoading}
        error={list.error}
        empty="No entries."
        columns={[
          { header: "Seq", accessorKey: "seq" },
          {
            header: "Time",
            accessorKey: "occurred_at",
            cell: (c) => dateTime(c.row.original.occurred_at),
          },
          { header: "Action", accessorKey: "action" },
          {
            header: "Target",
            accessorFn: (r) => [r.target_type, r.target_id].filter(Boolean).join(" "),
          },
          {
            header: "Detail",
            accessorFn: (r) => JSON.stringify(r.detail),
            cell: (c) => <code className="text-xs">{JSON.stringify(c.row.original.detail)}</code>,
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
    </div>
  );
}

function RiskConfig() {
  const cur = useQuery({ queryKey: ["risk-config"], queryFn: () => api<RC>("/admin/risk-config") });
  const hist = useQuery({
    queryKey: ["risk-config-history"],
    queryFn: () =>
      api<{ items: { version: number; created_at: string; config: Record<string, unknown> }[] }>(
        "/admin/risk-config/history",
      ),
  });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const c = cur.data?.config ?? {};
  const val = (k: string) => draft[k] ?? (c[k] === undefined ? "" : JSON.stringify(c[k]));
  const publish = useAction(
    () => {
      const body: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(draft)) if (v.trim()) body[k] = JSON.parse(v);
      return api("/admin/risk-config", { method: "PUT", json: body });
    },
    {
      success: "New version published",
      invalidate: [["risk-config"], ["risk-config-history"]],
      onDone: () => setDraft({}),
    },
  );
  const fields: [string, string, string][] = [
    ["severity_weights", "Severity weights (4 numbers)", "[0.05, 0.15, 0.3, 0.6]"],
    ["half_life_regulator_days", "Regulator half-life (days)", "365"],
    ["half_life_news_days", "News half-life (days)", "30"],
    ["impact_cap", "Impact cap per event (0 to 1)", "0.6"],
    ["level_thresholds", "Level thresholds (3 numbers)", "[30, 50, 70]"],
    ["relation_weights", "Relationship weights (JSON object)", '{"direct": 1.0}'],
    ["source_reliability", "Source reliability (JSON object)", '{"regulator": 1.0}'],
  ];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title={`Active configuration${cur.data ? `, version ${cur.data.version}` : ""}`}>
        <p className="mb-3 text-sm text-slate-600">
          Changing a value publishes a new version. Values stay within bounds the platform allows,
          and past scores keep the version that produced them.
        </p>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            try {
              publish.mutate(undefined);
            } catch (err) {
              useUi.getState().toast("error", errText(err));
            }
          }}
        >
          {fields.map(([k, l, ex]) => (
            <Field
              key={k}
              id={`rc-${k}`}
              label={l}
              hint={`Current: ${val(k) || "default"}. Example ${ex}`}
            >
              {(a) => (
                <Input
                  {...a}
                  className="font-mono text-sm"
                  value={draft[k] ?? ""}
                  onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
                  placeholder="Leave empty to keep"
                />
              )}
            </Field>
          ))}
          <Button
            type="submit"
            disabled={publish.isPending || !Object.values(draft).some((v) => v.trim())}
          >
            Publish a new version
          </Button>
        </form>
      </Panel>
      <Panel title="Version history">
        <ul className="space-y-2">
          {hist.data?.items.map((h) => (
            <li key={h.version} className="border-line rounded-[10px] border p-3 text-sm">
              <p className="text-ink font-medium">
                Version {h.version}{" "}
                <span className="font-normal text-slate-600">{dateTime(h.created_at)}</span>
              </p>
              <pre className="mt-1 max-h-32 overflow-auto text-xs text-slate-600" tabIndex={0}>
                {JSON.stringify(h.config, null, 1)}
              </pre>
            </li>
          ))}
        </ul>
        {hist.data?.items.length === 0 && (
          <p className="text-sm text-slate-600">Only the platform default has been used.</p>
        )}
      </Panel>
    </div>
  );
}

function Security() {
  const t = useQuery({
    queryKey: ["tenant-settings"],
    queryFn: () => api<Tenant>("/tenants/current"),
  });
  const patch = useAction(
    (b: Partial<Tenant>) => api("/tenants/current", { method: "PATCH", json: b }),
    { success: "Settings saved", invalidate: [["tenant-settings"], ["tenant"]] },
  );
  const [days, setDays] = useState("");
  if (!t.data) return null;
  return (
    <Panel title="Security and data settings">
      <div className="space-y-5">
        <label className="text-ink flex items-start gap-3 text-sm">
          <Checkbox
            checked={t.data.require_mfa}
            onChange={(e) => patch.mutate({ require_mfa: e.target.checked })}
          />
          <span>
            <span className="font-medium">Require multi-factor sign-in for everyone</span>
            <span className="block text-slate-600">
              Administrators always need it. Turn this on to require it for every user in this
              tenant.
            </span>
          </span>
        </label>
        <label className="text-ink flex items-start gap-3 text-sm">
          <Checkbox
            checked={t.data.share_feedback_for_training}
            onChange={(e) => patch.mutate({ share_feedback_for_training: e.target.checked })}
          />
          <span>
            <span className="font-medium">Share review decisions to improve matching</span>
            <span className="block text-slate-600">
              Off by default. When on, decisions are stored without any tenant identifier.
            </span>
          </span>
        </label>
        <form
          className="flex items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            patch.mutate({ retention_days: Number(days) });
          }}
        >
          <Field
            id="ret"
            label="Retention (days)"
            hint={`Currently ${t.data.retention_days}. Between 30 and 3,650. The scheduled purge job is not running yet.`}
          >
            {(a) => (
              <Input
                {...a}
                type="number"
                min={30}
                max={3650}
                className="w-40"
                value={days}
                onChange={(e) => setDays(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" variant="secondary" disabled={!days}>
            Save
          </Button>
        </form>
        <p className="text-sm text-slate-600">
          Session length: access tokens last minutes and renew silently; the application signs out
          after 30 minutes without activity. Per-tenant session lengths are not configurable yet.
        </p>
      </div>
    </Panel>
  );
}

export default function AdminPage() {
  const me = useMe().data;
  return (
    <>
      <PageHeader
        title="Administration"
        text="Users and roles, API keys, the audit log, risk configuration, and security settings."
      />
      <Tabs
        label="Administration sections"
        items={[
          { id: "users", label: "Users", content: <Users /> },
          { id: "keys", label: "API keys", content: <Keys /> },
          ...(can(me, "view_audit")
            ? [{ id: "audit", label: "Audit log", content: <AuditLog /> }]
            : []),
          { id: "risk", label: "Risk configuration", content: <RiskConfig /> },
          { id: "security", label: "Security", content: <Security /> },
        ]}
      />
    </>
  );
}
