import type { ReactNode } from "react";

/** A browser window frame used around interface illustrations. */
export function BrowserFrame({
  children,
  url = "app.provenance-risk.example/review",
}: {
  children: ReactNode;
  url?: string;
}) {
  return (
    <div className="border-line overflow-hidden rounded-[12px] border bg-white shadow-[var(--shadow-3)]">
      <div className="border-line flex items-center gap-2 border-b bg-slate-50 px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-slate-300" />
        <span className="size-2.5 rounded-full bg-slate-300" />
        <span className="size-2.5 rounded-full bg-slate-300" />
        <span className="ml-3 min-w-0 truncate rounded-md bg-white px-3 py-0.5 font-mono text-xs text-slate-600">
          {url}
        </span>
      </div>
      {children}
    </div>
  );
}
