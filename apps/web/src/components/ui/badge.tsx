import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const badge = cva("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium", {
  variants: {
    tone: {
      neutral: "bg-slate-100 text-slate-700",
      brand: "bg-brand-100 text-brand-600",
      success: "bg-[#e3f4ec] text-[#176e47]",
      warning: "bg-[#fbeed6] text-[#8a5200]",
      danger: "bg-[#fbe4e1] text-[#9b2c20]",
      low: "bg-[#e3f4ec] text-[#176e47]",
      medium: "bg-[#fbeed6] text-[#8a5200]",
      high: "bg-[#fbe0d4] text-[#9a3a12]",
      critical: "bg-[#fbe4e1] text-[#9b2c20]",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({
  tone,
  className,
  children,
}: VariantProps<typeof badge> & { className?: string; children: React.ReactNode }) {
  return <span className={cn(badge({ tone }), className)}>{children}</span>;
}
