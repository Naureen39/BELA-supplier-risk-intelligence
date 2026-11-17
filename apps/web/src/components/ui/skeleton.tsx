import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-[8px] bg-slate-200", className)} />;
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-[12px] border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="text-ink text-[16px] font-medium">{title}</p>
      {children && <div className="mt-2 text-[15px] text-slate-600">{children}</div>}
    </div>
  );
}
