"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Wordmark } from "@/components/art/logo";

const STATEMENTS = [
  {
    h: "Every record shown with its source",
    p: "Each event links to the public record it came from, with the date.",
  },
  {
    h: "Uncertain matches go to a person",
    p: "The platform never attaches a record to a company without a stored score and route.",
  },
  { h: "Risk signals are leads", p: "They are for human review and not statements of fault." },
];

function BrandPanel() {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setI((n) => (n + 1) % STATEMENTS.length), 6000);
    return () => clearInterval(id);
  }, []);
  const s = STATEMENTS[i]!;
  return (
    <aside className="bg-ink relative hidden flex-col justify-between overflow-hidden p-12 text-white lg:flex">
      <div
        aria-hidden
        className="absolute inset-0 bg-[radial-gradient(60%_50%_at_20%_10%,#1f5fbf55,transparent),radial-gradient(50%_40%_at_90%_90%,#00a3a355,transparent)]"
      />
      <div className="relative">
        <Wordmark light />
      </div>
      <div className="relative max-w-md" aria-live="polite">
        <h2 className="text-h2 text-white">{s.h}</h2>
        <p className="mt-3 text-lg leading-8 text-slate-300">{s.p}</p>
        <div className="mt-8 flex gap-2" aria-hidden>
          {STATEMENTS.map((_, n) => (
            <span
              key={n}
              className={`h-1 w-8 rounded-full ${n === i ? "bg-white" : "bg-slate-600"}`}
            />
          ))}
        </div>
      </div>
      <p className="relative rounded-[8px] border border-slate-600 px-4 py-3 text-sm text-slate-300">
        Demo data. Tenants, revenue, and portfolios in this environment are synthetic.
      </p>
    </aside>
  );
}

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <main id="main" className="flex flex-col justify-center bg-white px-6 py-12 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <Link href="/" className="mb-10 inline-block lg:hidden" aria-label="Provenance Risk home">
            <Wordmark />
          </Link>
          <h1 className="text-h2">{title}</h1>
          {subtitle && <p className="mt-2 text-[15px] leading-7 text-slate-700">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          <p className="mt-10 text-xs leading-5 text-slate-600">
            Risk signals are leads for human review and not statements of fault.
          </p>
        </div>
      </main>
      <BrandPanel />
    </div>
  );
}
