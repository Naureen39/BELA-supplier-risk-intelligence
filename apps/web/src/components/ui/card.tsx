import { cn } from "@/lib/cn";

export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "border-line rounded-[12px] border bg-white shadow-[var(--shadow-1)]",
        className,
      )}
      {...p}
    />
  );
}

export function HoverCard({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <Card
      className={cn(
        "transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-[var(--shadow-2)]",
        className,
      )}
      {...p}
    />
  );
}
