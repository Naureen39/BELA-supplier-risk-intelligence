import Link from "next/link";
import { ChevronRight } from "lucide-react";

export function Breadcrumbs({ items }: { items: { title: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-slate-600">
      <ol className="flex flex-wrap items-center gap-1">
        {items.map((it, i) => (
          <li key={it.title} className="flex items-center gap-1">
            {it.href ? (
              <Link href={it.href} className="hover:text-ink hover:underline">
                {it.title}
              </Link>
            ) : (
              <span aria-current="page" className="text-ink">
                {it.title}
              </span>
            )}
            {i < items.length - 1 && <ChevronRight className="size-4" aria-hidden />}
          </li>
        ))}
      </ol>
    </nav>
  );
}
