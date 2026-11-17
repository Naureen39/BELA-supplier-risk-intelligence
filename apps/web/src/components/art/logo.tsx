export function LogoMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#0B1B33" />
      <path
        d="M9 22V10h7a4 4 0 0 1 0 8h-4"
        fill="none"
        stroke="#fff"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="9" cy="22" r="2.4" fill="#00A3A3" />
      <circle cx="22" cy="22" r="2.4" fill="#2F74D8" />
      <path d="M16 18l5 3" stroke="#2F74D8" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark />
      <span
        className={`text-[19px] font-semibold tracking-tight ${light ? "text-white" : "text-ink"}`}
      >
        Provenance <span className={light ? "text-slate-300" : "text-slate-600"}>Risk</span>
      </span>
    </span>
  );
}
