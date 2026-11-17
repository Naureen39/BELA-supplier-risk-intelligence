import type { ReactNode } from "react";

export function Stepper({
  steps,
}: {
  steps: { title: string; text: string; visual?: ReactNode }[];
}) {
  return (
    <ol className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
      {steps.map((s, i) => (
        <li
          key={s.title}
          className="border-line relative rounded-[12px] border bg-white p-6 shadow-[var(--shadow-1)]"
        >
          <span className="bg-brand-100 text-brand-600 mb-4 flex size-9 items-center justify-center rounded-full text-sm font-semibold">
            {i + 1}
          </span>
          {s.visual && <div className="mb-4">{s.visual}</div>}
          <h3 className="text-h4 text-ink">{s.title}</h3>
          <p className="mt-2 text-[15px] leading-7 text-slate-700">{s.text}</p>
        </li>
      ))}
    </ol>
  );
}
