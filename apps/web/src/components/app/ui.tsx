"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { useUi } from "@/lib/app/store";

export const DEMO = <Badge tone="warning">Demo data</Badge>;

export function PageHeader({
  title,
  text,
  actions,
  demo,
}: {
  title: string;
  text?: string;
  actions?: ReactNode;
  demo?: boolean;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight">
          {title}
          {demo && DEMO}
        </h1>
        {text && <p className="mt-1 max-w-2xl text-[15px] leading-6 text-slate-600">{text}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function RiskBadge({
  level,
  score,
}: {
  level: string | null | undefined;
  score?: number | string | null;
}) {
  if (!level) return <Badge tone="neutral">Not scored</Badge>;
  const tone = (["low", "medium", "high", "critical"].includes(level) ? level : "neutral") as
    "low" | "medium" | "high" | "critical" | "neutral";
  return (
    <Badge tone={tone}>
      {level[0]?.toUpperCase()}
      {level.slice(1)}
      {score != null && score !== "" ? `: ${Number(score).toFixed(0)}` : ""}
    </Badge>
  );
}

export const SEVERITY = ["", "Low", "Moderate", "Serious", "Severe"];
export function SeverityBadge({ severity }: { severity: number }) {
  const tone = (["neutral", "low", "medium", "high", "critical"] as const)[severity] ?? "neutral";
  return <Badge tone={tone}>{SEVERITY[severity] ?? `Level ${severity}`}</Badge>;
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const text = error instanceof Error ? error.message : "The data could not be loaded.";
  return (
    <div role="alert" className="border-danger/40 rounded-[12px] border bg-white p-6 text-center">
      <AlertTriangle className="text-danger mx-auto mb-2 size-6" aria-hidden />
      <p className="text-ink font-medium">This could not be loaded</p>
      <p className="mt-1 text-sm text-slate-600">{text}</p>
      {retry && (
        <Button className="mt-4" size="sm" variant="secondary" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function KpiCard({
  label,
  value,
  change,
  better = "up",
  sparkline,
  note,
}: {
  label: string;
  value: string;
  change?: number | null;
  better?: "up" | "down";
  sparkline?: (number | null)[];
  note?: string;
}) {
  const good = change == null ? null : better === "up" ? change >= 0 : change <= 0;
  const pts = (sparkline ?? []).filter((v): v is number => v != null);
  const lo = Math.min(...pts);
  const hi = Math.max(...pts);
  return (
    <Card className="p-4">
      <p className="text-sm text-slate-600">{label}</p>
      <p className="text-ink mt-1 text-2xl font-semibold tracking-tight">{value}</p>
      <div className="mt-1 flex items-center justify-between gap-2 text-xs">
        {change != null ? (
          <span className={cn("font-medium", good ? "text-success" : "text-danger")}>
            {change >= 0 ? "Up" : "Down"} {Math.abs(change).toFixed(1)}%
            <span className="sr-only"> versus the previous period</span>
          </span>
        ) : (
          <span className="text-slate-600">{note ?? ""}</span>
        )}
        {pts.length > 1 && (
          <svg viewBox="0 0 60 20" className="h-5 w-16" aria-hidden>
            <polyline
              fill="none"
              stroke="var(--color-chart-1)"
              strokeWidth="1.6"
              points={pts
                .map(
                  (v, i) =>
                    `${(i / (pts.length - 1)) * 60},${hi === lo ? 10 : 18 - ((v - lo) / (hi - lo)) * 16}`,
                )
                .join(" ")}
            />
          </svg>
        )}
      </div>
    </Card>
  );
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  text,
  confirmLabel,
  destructive,
  onConfirm,
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  text: string;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 rounded-[12px] bg-white p-6 shadow-[var(--shadow-3)]">
          <Dialog.Title className="text-ink text-lg font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-[15px] leading-6 text-slate-600">
            {text}
          </Dialog.Description>
          {children}
          <div className="mt-6 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="secondary">Cancel</Button>
            </Dialog.Close>
            <Button
              variant={destructive ? "destructive" : "primary"}
              onClick={() => {
                onConfirm();
                onOpenChange(false);
              }}
            >
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Toaster() {
  const toasts = useUi((s) => s.toasts);
  const dismiss = useUi((s) => s.dismiss);
  return (
    <div
      role="region"
      aria-label="Notifications"
      className="pointer-events-none fixed right-4 bottom-4 z-[70] flex w-[min(92vw,360px)] flex-col gap-2"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role={t.tone === "error" ? "alert" : "status"}
          className="border-line pointer-events-auto flex items-start gap-3 rounded-[10px] border bg-white p-3 shadow-[var(--shadow-2)]"
        >
          {t.tone === "success" ? (
            <CheckCircle2 className="text-success mt-0.5 size-5 shrink-0" aria-hidden />
          ) : t.tone === "error" ? (
            <AlertTriangle className="text-danger mt-0.5 size-5 shrink-0" aria-hidden />
          ) : (
            <Info className="text-link mt-0.5 size-5 shrink-0" aria-hidden />
          )}
          <p className="text-ink flex-1 text-sm">{t.text}</p>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => dismiss(t.id)}
            className="rounded p-1 hover:bg-slate-100"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}

export function Panel({
  title,
  actions,
  children,
  className,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("p-5", className)}>
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-ink text-base font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </Card>
  );
}
