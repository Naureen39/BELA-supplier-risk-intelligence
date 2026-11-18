"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { PageHeader, Panel, SkeletonRows, ErrorState, ConfirmDialog } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/field";
import { api } from "@/lib/api";
import { label } from "@/lib/app/format";
import { flat, useAction, useCursorList } from "@/lib/app/hooks";
import type { Candidate, ReviewRow } from "@/lib/app/types";

interface Detail {
  id: string;
  status: string;
  supplier_id: string;
  uploaded: Record<string, string | null>;
  candidates: Candidate[];
}

const AGREE: Record<string, "success" | "danger" | "neutral"> = {
  agree: "success",
  disagree: "danger",
  unknown: "neutral",
};
const FIELDS = ["name", "state", "city", "country", "cik", "lei", "ticker", "parent", "industry"];

function Comparison({
  d,
  chosen,
  onChoose,
}: {
  d: Detail;
  chosen: number | null;
  onChoose: (id: number) => void;
}) {
  return (
    <div className="space-y-4">
      {d.candidates.map((c, i) => (
        <section
          key={c.company_id}
          aria-label={`Candidate ${i + 1}: ${c.name}`}
          className={`rounded-[12px] border p-4 ${chosen === c.company_id ? "border-brand-600 ring-brand-600 ring-1" : "border-line"}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="text-ink flex items-center gap-2 font-medium">
              <input
                type="radio"
                name="candidate"
                checked={chosen === c.company_id}
                onChange={() => onChoose(c.company_id)}
                className="accent-brand-600"
              />
              {i + 1}. {c.name}
            </label>
            <Badge
              tone={c.probability >= 0.8 ? "success" : c.probability >= 0.5 ? "warning" : "neutral"}
            >
              {(c.probability * 100).toFixed(0)}% match
            </Badge>
          </div>
          <p className="mt-1 text-xs text-slate-600">
            Retrieval {c.scores?.retrieval?.toFixed(2) ?? "n/a"} &middot; Splink weight{" "}
            {c.scores?.splink_weight?.toFixed(1) ?? "n/a"} &middot; BLINK{" "}
            {c.scores?.blink != null ? c.scores.blink.toFixed(2) : "not run"} &middot; Sources{" "}
            {(c.sources ?? []).join(", ") || "n/a"}
          </p>
          <p className="mt-2 text-xs text-slate-600">
            Fields with no data on either side are not listed.
          </p>
          <table className="mt-3 w-full text-left text-sm">
            <caption className="sr-only">Field comparison for {c.name}</caption>
            <thead>
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium text-slate-600">
                  Field
                </th>
                <th scope="col" className="py-1 pr-3 font-medium text-slate-600">
                  Uploaded
                </th>
                <th scope="col" className="py-1 pr-3 font-medium text-slate-600">
                  Candidate
                </th>
                <th scope="col" className="py-1 font-medium text-slate-600">
                  Agreement
                </th>
              </tr>
            </thead>
            <tbody>
              {FIELDS.map((f) => {
                const x = c.comparison?.[f];
                if (!x || (x.uploaded == null && x.candidate == null && x.similarity == null))
                  return null; // fields with no data on either side are left out
                const state =
                  x.agreement ??
                  (x.similarity != null ? (x.similarity > 0.85 ? "agree" : "disagree") : "unknown");
                return (
                  <tr key={f} className="border-line border-t">
                    <th scope="row" className="text-ink py-1.5 pr-3 font-normal">
                      {label(f)}
                    </th>
                    <td className="py-1.5 pr-3 font-mono text-xs text-slate-700">
                      {x.uploaded ?? "n/a"}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-xs text-slate-700">
                      {x.candidate ?? "n/a"}
                    </td>
                    <td className="py-1.5">
                      <Badge tone={AGREE[state] ?? "neutral"}>
                        {state === "agree"
                          ? "Agrees"
                          : state === "disagree"
                            ? "Differs"
                            : "Unknown"}
                        {x.similarity != null ? ` ${(x.similarity * 100).toFixed(0)}%` : ""}
                      </Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

export default function ReviewsPage() {
  const list = useCursorList<ReviewRow>(["reviews"], "/reviews?limit=100");
  const rows = flat(list.data);
  const [sel, setSel] = useState<string | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<null | "reject" | "mark_unresolved" | "not_in_database">(
    null,
  );
  const [minP, setMinP] = useState("0.85");
  const [bulk, setBulk] = useState(false);
  const current = sel ?? rows[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["review", current],
    enabled: !!current,
    queryFn: () => api<Detail>(`/reviews/${current}`),
  });

  const decide = useAction(
    (v: { action: string; company_id?: number | null }) =>
      api(`/reviews/${current}`, { method: "PATCH", json: v }),
    {
      success: "Decision saved",
      invalidate: [["reviews"], ["suppliers"], ["overview"]],
      onDone: () => {
        setSel(null);
        setChosen(null);
      },
    },
  );
  const bulkAccept = useAction(
    () =>
      api<{ accepted: number; remaining: number }>("/reviews/bulk-accept", {
        json: { min_probability: Number(minP) },
      }),
    { success: "Bulk accept finished", invalidate: [["reviews"], ["suppliers"]] },
  );

  const top = detail.data?.candidates[0]?.company_id ?? null;
  const act = useCallback(
    (action: string) =>
      decide.mutate(action === "choose_other" ? { action, company_id: chosen } : { action }),
    [decide, chosen],
  );

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (
        e.ctrlKey ||
        e.metaKey ||
        e.altKey ||
        (e.target as HTMLElement).closest("input, textarea, select, [role=dialog]")
      )
        return;
      const i = rows.findIndex((r) => r.id === current);
      if (e.key === "j" && rows[i + 1]) {
        setSel(rows[i + 1]!.id);
        setChosen(null);
      } else if (e.key === "k" && rows[i - 1]) {
        setSel(rows[i - 1]!.id);
        setChosen(null);
      } else if (e.key === "a" && detail.data?.candidates.length)
        act(chosen && chosen !== top ? "choose_other" : "accept");
      else if (e.key === "r") setConfirm("reject");
      else if (e.key === "u") setConfirm("mark_unresolved");
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [rows, current, detail.data, chosen, top, act]);

  return (
    <>
      <PageHeader
        title="Review queue"
        text="Uploaded records the matcher was not sure about. Decide each one with the evidence beside it."
        actions={
          <Button variant="secondary" onClick={() => setBulk(true)} disabled={!rows.length}>
            Bulk accept
          </Button>
        }
      />
      <p className="mb-4 text-xs text-slate-600">
        Keyboard: J and K move between records, A accepts (or confirms your chosen candidate), R
        rejects, U marks unresolved.
      </p>
      {list.isLoading ? (
        <SkeletonRows />
      ) : list.error ? (
        <ErrorState error={list.error} retry={() => void list.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title="The review queue is empty">
          Records the matcher is unsure about appear here after an upload.
        </EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <nav
            aria-label="Open reviews"
            className="border-line max-h-[70vh] overflow-auto rounded-[12px] border bg-white"
          >
            <ul className="divide-line divide-y">
              {rows.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    aria-current={r.id === current ? "true" : undefined}
                    onClick={() => {
                      setSel(r.id);
                      setChosen(null);
                    }}
                    className={`block w-full px-4 py-3 text-left text-sm ${r.id === current ? "bg-brand-100" : "hover:bg-slate-50"}`}
                  >
                    <span className="text-ink block font-medium">{r.uploaded_name}</span>
                    <span className="block text-xs text-slate-600">
                      {r.attributes?.state ?? ""} {r.tier ? `${label(r.tier)}, ` : ""}best match{" "}
                      {((r.candidates[0]?.probability ?? 0) * 100).toFixed(0)}%
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <Panel title={detail.data ? `Record: ${detail.data.uploaded.name}` : "Record"}>
            {detail.isLoading ? (
              <SkeletonRows rows={4} />
            ) : detail.error || !detail.data ? (
              <ErrorState error={detail.error} />
            ) : (
              <>
                <p className="mb-4 text-sm text-slate-600">
                  Uploaded:{" "}
                  {Object.entries(detail.data.uploaded)
                    .filter(([, v]) => v)
                    .map(([k, v]) => `${label(k)} ${v}`)
                    .join(", ")}
                </p>
                <Comparison d={detail.data} chosen={chosen ?? top} onChoose={setChosen} />
                <div className="mt-5 flex flex-wrap gap-2">
                  <Button
                    onClick={() => act(chosen && chosen !== top ? "choose_other" : "accept")}
                    disabled={decide.isPending || !detail.data.candidates.length}
                  >
                    {chosen && chosen !== top
                      ? "Choose this candidate"
                      : "Accept the top candidate"}
                  </Button>
                  <Button variant="secondary" onClick={() => setConfirm("reject")}>
                    None of these
                  </Button>
                  <Button variant="secondary" onClick={() => setConfirm("mark_unresolved")}>
                    Mark unresolved
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirm("not_in_database")}>
                    Not in the database
                  </Button>
                </div>
              </>
            )}
          </Panel>
        </div>
      )}
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Confirm this decision"
        text={
          confirm === "reject"
            ? "No candidate is the right company. The record stays unlinked."
            : confirm === "mark_unresolved"
              ? "The record will be marked unresolved and left out of monitoring."
              : "The company is not in the knowledge base. The record is marked accordingly."
        }
        confirmLabel="Confirm"
        onConfirm={() => confirm && decide.mutate({ action: confirm })}
      />
      <ConfirmDialog
        open={bulk}
        onOpenChange={setBulk}
        title="Bulk accept"
        text={`Accept the top candidate of every open review at or above ${(Number(minP) * 100).toFixed(0)}% with a clear margin over the runner-up. Choose the threshold below, then confirm.`}
        confirmLabel="Accept reviews"
        onConfirm={() => bulkAccept.mutate(undefined)}
      >
        <div className="mt-4">
          <label htmlFor="minp" className="text-ink mb-1 block text-sm font-medium">
            Minimum confidence
          </label>
          <Input
            id="minp"
            type="number"
            step="0.05"
            min="0.5"
            max="1"
            value={minP}
            onChange={(e) => setMinP(e.target.value)}
            className="w-28"
          />
        </div>
      </ConfirmDialog>
    </>
  );
}
