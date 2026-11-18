"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { download, api, ApiRequestError } from "@/lib/api";
import { errText } from "@/lib/app/hooks";
import { useUi } from "@/lib/app/store";
import { Panel } from "./ui";

interface Preview {
  columns: string[];
  mapping: Record<string, string>;
  unmapped_fields: string[];
  valid_rows: number;
  invalid_rows: number;
  errors: { row?: number; error?: string; message?: string }[];
  sample: Record<string, string>[];
  row_limit: number;
}
interface UploadView {
  id: string;
  status: string;
  total_rows?: number;
  auto_resolved?: number;
  needs_review?: number;
  unresolved?: number;
}

const STEPS = ["File", "Columns", "Check", "Result"];

async function post<T>(
  path: string,
  file: File,
  mapping: Record<string, string> | null,
): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  if (mapping) fd.append("mapping", JSON.stringify(mapping));
  return api<T>(path, { method: "POST", body: fd });
}

export function UploadWizard({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const status = useQuery({
    queryKey: ["upload", uploadId],
    enabled: !!uploadId,
    queryFn: () => api<UploadView>(`/uploads/${uploadId}`),
    refetchInterval: (q) =>
      q.state.data && ["complete", "failed"].includes(q.state.data.status) ? false : 1000,
  });

  async function runPreview(f: File, m: Record<string, string> | null) {
    setBusy(true);
    setError("");
    try {
      const p = await post<Preview>("/uploads/preview", f, m);
      setPreview(p);
      setMapping(p.mapping);
      setStep(1);
    } catch (e) {
      setError(e instanceof ApiRequestError && e.status === 422 ? errText(e) : errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const u = await post<UploadView>("/uploads", file, mapping);
      setUploadId(u.id);
      setStep(3);
      void qc.invalidateQueries({ queryKey: ["suppliers"] });
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const done = status.data && ["complete", "failed"].includes(status.data.status);
  return (
    <Panel
      title="Upload suppliers"
      actions={
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      <ol className="mb-5 flex flex-wrap gap-2 text-sm" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li
            key={s}
            aria-current={i === step ? "step" : undefined}
            className={`rounded-full px-3 py-1 ${i === step ? "bg-brand-600 text-[#ffffff]" : i < step ? "bg-brand-100 text-link" : "bg-slate-100 text-slate-600"}`}
          >
            {i + 1}. {s}
          </li>
        ))}
      </ol>
      {error && (
        <p role="alert" className="mb-4 rounded-[8px] bg-[#fbe4e1] p-3 text-sm text-[#9b2c20]">
          {error}
        </p>
      )}

      {step === 0 && (
        <div className="space-y-4">
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              download("/uploads/template", "supplier_template.csv").catch((e) =>
                toast("error", errText(e)),
              )
            }
          >
            <Download className="size-4" aria-hidden /> Download the CSV template
          </Button>
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files[0];
              if (f) {
                setFile(f);
                void runPreview(f, null);
              }
            }}
            className="rounded-[12px] border-2 border-dashed border-slate-300 p-8 text-center"
          >
            <UploadCloud className="mx-auto mb-2 size-8 text-slate-500" aria-hidden />
            <p className="text-ink text-sm">Drag a CSV file here, or</p>
            <input
              ref={input}
              id="upload-file"
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  setFile(f);
                  void runPreview(f, null);
                }
              }}
            />
            <Button
              className="mt-3"
              variant="secondary"
              disabled={busy}
              onClick={() => input.current?.click()}
            >
              {busy ? "Reading the file" : "Choose a file"}
            </Button>
            <p className="mt-3 text-xs text-slate-600">
              CSV only. Up to 10,000 rows. Nothing is stored until you confirm.
            </p>
          </div>
        </div>
      )}

      {step === 1 && preview && file && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Match each field to a column in {file.name}. Name is required.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {[...Object.keys(preview.mapping), ...preview.unmapped_fields].map((field) => (
              <div key={field}>
                <label htmlFor={`map-${field}`} className="text-ink mb-1 block text-sm font-medium">
                  {field}
                </label>
                <Select
                  id={`map-${field}`}
                  value={mapping[field] ?? ""}
                  onChange={(e) =>
                    setMapping((m) => {
                      const n = { ...m };
                      if (e.target.value) n[field] = e.target.value;
                      else delete n[field];
                      return n;
                    })
                  }
                >
                  <option value="">Not in this file</option>
                  {preview.columns.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </Select>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <Button
              onClick={() => runPreview(file, mapping).then(() => setStep(2))}
              disabled={busy || !mapping.name}
            >
              Check the file
            </Button>
            <Button variant="ghost" onClick={() => setStep(0)}>
              Back
            </Button>
          </div>
        </div>
      )}

      {step === 2 && preview && (
        <div className="space-y-4">
          <p className="text-ink text-sm">
            {preview.valid_rows} rows are ready. {preview.invalid_rows} rows have problems and will
            be skipped.
          </p>
          {preview.errors.length > 0 && (
            <ul className="list-disc pl-5 text-sm text-slate-700">
              {preview.errors.map((e, i) => (
                <li key={i}>
                  Row {e.row ?? "?"}: {e.error ?? e.message}
                </li>
              ))}
            </ul>
          )}
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Sample rows">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">First rows of the file</caption>
              <thead>
                <tr>
                  {Object.keys(preview.sample[0] ?? {}).map((k) => (
                    <th key={k} scope="col" className="text-ink px-2 py-1 font-medium">
                      {k}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample.map((r, i) => (
                  <tr key={i} className="border-line border-t">
                    {Object.values(r).map((v, j) => (
                      <td key={j} className="px-2 py-1 text-slate-700">
                        {String(v ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-2">
            <Button onClick={start} disabled={busy || preview.valid_rows === 0}>
              Upload {preview.valid_rows} suppliers
            </Button>
            <Button variant="ghost" onClick={() => setStep(1)}>
              Back
            </Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4" aria-live="polite">
          {!done ? (
            <p className="text-ink text-sm" role="status">
              Resolving suppliers. This page updates as rows are matched.
            </p>
          ) : status.data?.status === "failed" ? (
            <p role="alert" className="text-danger text-sm">
              The upload failed. Try again or contact support.
            </p>
          ) : (
            <>
              <p className="text-ink font-medium">Upload complete</p>
              <dl className="grid grid-cols-3 gap-3 text-center">
                {[
                  ["Auto-resolved", status.data?.auto_resolved],
                  ["Needs review", status.data?.needs_review],
                  ["Unresolved", status.data?.unresolved],
                ].map(([k, v]) => (
                  <div key={String(k)} className="rounded-[10px] bg-slate-50 p-3">
                    <dt className="text-xs text-slate-600">{k}</dt>
                    <dd className="text-ink text-2xl font-semibold">{v ?? 0}</dd>
                  </div>
                ))}
              </dl>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  onClick={() =>
                    download(`/uploads/${uploadId}/export`, "upload_results.csv").catch((e) =>
                      toast("error", errText(e)),
                    )
                  }
                >
                  Export results
                </Button>
                <Button onClick={onClose}>Done</Button>
              </div>
            </>
          )}
        </div>
      )}
    </Panel>
  );
}
