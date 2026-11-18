"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { PageHeader, Panel } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { api } from "@/lib/api";
import { dateTime, label } from "@/lib/app/format";
import { useAction } from "@/lib/app/hooks";
import { useMe } from "@/lib/app/session";
import { useUi } from "@/lib/app/store";
import Link from "next/link";

interface Setup {
  secret: string;
  otpauth_uri: string;
  recovery_codes: string[];
}

export default function SettingsPage() {
  const me = useMe().data;
  const qc = useQueryClient();
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () =>
      api<{
        items: {
          id: string;
          started_at: string;
          last_seen_at: string;
          user_agent: string | null;
          current: boolean;
        }[];
      }>("/auth/sessions"),
  });
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const begin = useAction(() => api<Setup>("/auth/mfa/setup", { json: {} }), { onDone: setSetup });
  const confirm = useAction(() => api("/auth/mfa/verify", { json: { code } }), {
    success: "Multi-factor sign-in is on",
    onDone: () => {
      setSetup(null);
      setCode("");
      void qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
  return (
    <>
      <PageHeader
        title="Settings"
        text="Your profile, multi-factor sign-in, active sessions, and display."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Profile">
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-xs text-slate-600">Email</dt>
              <dd className="text-ink">{me?.email}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-600">Role</dt>
              <dd className="text-ink">{label(me?.role ?? "")}</dd>
            </div>
          </dl>
          <div className="mt-4">
            <span className="text-ink mr-3 text-sm">Theme</span>
            <div className="inline-flex gap-1" role="group" aria-label="Theme">
              {(["light", "dark"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={theme === t}
                  onClick={() => setTheme(t)}
                  className={`h-9 rounded-[8px] border px-3 text-sm ${theme === t ? "border-brand-600 bg-brand-600 text-[#ffffff]" : "border-line text-ink"}`}
                >
                  {label(t)}
                </button>
              ))}
            </div>
          </div>
        </Panel>
        <Panel title="Multi-factor sign-in">
          {me?.mfa_enabled ? (
            <Badge tone="success">On</Badge>
          ) : setup ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-600">
                Scan the code with an authenticator app, then enter the current code.
              </p>
              <div className="inline-block rounded-[10px] bg-white p-3">
                <QRCodeSVG value={setup.otpauth_uri} size={150} title="Authenticator setup code" />
              </div>
              <p className="text-ink font-mono text-sm break-all">{setup.secret}</p>
              <div>
                <p className="text-ink text-sm font-medium">Recovery codes (shown once)</p>
                <ul className="text-ink mt-1 grid grid-cols-2 gap-1 font-mono text-sm">
                  {setup.recovery_codes.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
              <form
                className="flex items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  confirm.mutate(undefined);
                }}
              >
                <Field id="mfa-code" label="Six-digit code">
                  {(a) => (
                    <Input
                      {...a}
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      className="w-36"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                    />
                  )}
                </Field>
                <Button type="submit" disabled={confirm.isPending || !code}>
                  Turn on
                </Button>
              </form>
            </div>
          ) : (
            <>
              <p className="mb-3 text-sm text-slate-600">
                Add a second step to sign-in with an authenticator app.
              </p>
              <Button onClick={() => begin.mutate(undefined)} disabled={begin.isPending}>
                Set up multi-factor sign-in
              </Button>
            </>
          )}
        </Panel>
        <Panel title="Active sessions">
          <ul className="divide-line divide-y text-sm">
            {sessions.data?.items.map((s) => (
              <li key={s.id} className="py-2">
                <span className="text-ink">{s.user_agent || "Unknown browser"}</span>
                {s.current && (
                  <Badge tone="brand" className="ml-2">
                    This session
                  </Badge>
                )}
                <span className="block text-xs text-slate-600">
                  Started {dateTime(s.started_at)}, last seen {dateTime(s.last_seen_at)}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-600">
            Ending other sessions from here is not available yet. Signing out ends this session.
          </p>
        </Panel>
        <Panel title="Notifications">
          <p className="text-sm text-slate-600">
            New alerts appear in the bell as they arrive. Email and webhook delivery are set per
            alert rule by managers.
          </p>
          <p className="mt-2 text-sm">
            <Link href="/app/alerts" className="text-link underline underline-offset-2">
              Open the alert queue
            </Link>
          </p>
        </Panel>
      </div>
    </>
  );
}
