import { Badge } from "@/components/ui/badge";
import { BrowserFrame } from "./browser-frame";
import { FamilyGraphic } from "@/components/art/illustrations";

const ROWS = [
  {
    upload: "ACME FOODS INC, OH",
    match: "Acme Foods, Inc.",
    p: 0.97,
    tone: "success" as const,
    label: "Accepted",
  },
  {
    upload: "Acme Foods Intl",
    match: "Acme Foods International Ltd",
    p: 0.71,
    tone: "warning" as const,
    label: "Review",
  },
  {
    upload: "NORTHFIELD MFG PLANT 3",
    match: "Northfield Manufacturing Co.",
    p: 0.88,
    tone: "brand" as const,
    label: "Suggested",
  },
];

/** An illustration of the review screen. It is drawn from the design system, not captured from a customer. */
export function ProductMock({
  variant = "review",
}: {
  variant?: "review" | "profile" | "family" | "analytics";
}) {
  if (variant === "family") {
    return (
      <BrowserFrame url="app.provenance-risk.example/graph">
        <div className="bg-white p-6">
          <FamilyGraphic />
        </div>
        <Caption />
      </BrowserFrame>
    );
  }
  if (variant === "profile") {
    return (
      <BrowserFrame url="app.provenance-risk.example/suppliers/profile">
        <div className="space-y-4 bg-white p-6">
          <div className="flex items-center justify-between">
            <p className="text-ink text-lg font-semibold">Acme Foods, Inc.</p>
            <Badge tone="high">High: score 61</Badge>
          </div>
          {[
            ["Workplace safety", "0.34"],
            ["Food safety recall", "0.29"],
            ["Environmental", "0.08"],
          ].map(([k, v]) => (
            <div key={k} className="flex items-center gap-3 text-sm">
              <span className="w-40 text-slate-700">{k}</span>
              <span className="h-2 flex-1 rounded-full bg-slate-100">
                <span
                  className="bg-brand-500 block h-2 rounded-full"
                  style={{ width: `${Number(v) * 220}%`, maxWidth: "100%" }}
                />
              </span>
              <span className="w-10 text-right font-mono text-slate-600">{v}</span>
            </div>
          ))}
        </div>
        <Caption />
      </BrowserFrame>
    );
  }
  if (variant === "analytics") {
    const bars = [38, 44, 41, 52, 58, 49, 63, 70, 66, 72];
    return (
      <BrowserFrame url="app.provenance-risk.example/analytics">
        <div className="bg-white p-6">
          <p className="text-ink mb-3 text-sm font-medium">Portfolio risk index</p>
          <svg
            viewBox="0 0 300 100"
            className="h-auto w-full"
            role="img"
            aria-label="A rising risk index line"
          >
            <path d="M0 70H300M0 50H300M0 30H300" stroke="#E2E8F0" />
            <polyline
              fill="none"
              stroke="#2F74D8"
              strokeWidth="2.5"
              points={bars.map((b, i) => `${i * 33},${100 - b}`).join(" ")}
            />
          </svg>
        </div>
        <Caption />
      </BrowserFrame>
    );
  }
  return (
    <BrowserFrame>
      <div className="bg-white">
        <div className="border-line text-ink border-b px-6 py-3 text-sm font-medium">
          Resolution review
        </div>
        <ul className="divide-line divide-y">
          {ROWS.map((r) => (
            <li
              key={r.upload}
              className="grid grid-cols-[1fr_auto] items-center gap-3 px-6 py-3.5 sm:grid-cols-[1fr_1fr_auto]"
            >
              <span className="font-mono text-xs text-slate-700">{r.upload}</span>
              <span className="text-ink hidden text-sm sm:block">{r.match}</span>
              <span className="flex items-center gap-2">
                <span className="font-mono text-xs text-slate-600">{r.p.toFixed(2)}</span>
                <Badge tone={r.tone}>{r.label}</Badge>
              </span>
            </li>
          ))}
        </ul>
      </div>
      <Caption />
    </BrowserFrame>
  );
}

function Caption() {
  return (
    <p className="border-line border-t bg-slate-50 px-4 py-2 text-xs text-slate-600">
      Illustration of the interface. Demo data.
    </p>
  );
}
