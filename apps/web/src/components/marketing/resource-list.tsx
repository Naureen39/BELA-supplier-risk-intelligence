"use client";

import Link from "next/link";
import { useState } from "react";
import { HoverCard } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import type { ArticleMeta } from "@/lib/articles";

export function ResourceList({ articles, tags }: { articles: ArticleMeta[]; tags: string[] }) {
  const [tag, setTag] = useState<string | null>(null);
  const shown = tag ? articles.filter((a) => a.tag === tag) : articles;
  return (
    <div>
      <div role="group" aria-label="Filter by tag" className="mb-8 flex flex-wrap gap-2">
        {[null, ...tags].map((t) => (
          <button
            key={t ?? "all"}
            type="button"
            aria-pressed={tag === t}
            onClick={() => setTag(t)}
            className={cn(
              "rounded-full border px-4 py-1.5 text-sm font-medium",
              tag === t
                ? "border-brand-600 bg-brand-600 text-white"
                : "border-line text-ink bg-white hover:bg-slate-50",
            )}
          >
            {t ?? "All"}
          </button>
        ))}
      </div>
      <ul className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {shown.map((a) => (
          <li key={a.slug}>
            <Link href={`/resources/${a.slug}`} className="group block h-full">
              <HoverCard className="flex h-full flex-col p-6">
                <p className="text-brand-600 text-xs font-medium tracking-wider uppercase">
                  {a.tag}
                </p>
                <h2 className="text-h4 group-hover:text-brand-600 mt-2">{a.title}</h2>
                <p className="mt-2 flex-1 text-[15px] leading-7 text-slate-700">{a.summary}</p>
                <p className="mt-4 text-sm text-slate-600">
                  <time dateTime={a.date}>
                    {new Date(a.date).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                      timeZone: "UTC",
                    })}
                  </time>{" "}
                  &middot; {a.readMinutes} min read
                </p>
              </HoverCard>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
