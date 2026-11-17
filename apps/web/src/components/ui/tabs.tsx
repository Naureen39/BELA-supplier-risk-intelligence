"use client";

import * as T from "@radix-ui/react-tabs";
import type { ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

export function Tabs({ items, label }: { items: TabItem[]; label: string }) {
  return (
    <T.Root defaultValue={items[0]?.id}>
      <T.List aria-label={label} className="border-line flex flex-wrap gap-1 border-b">
        {items.map((t) => (
          <T.Trigger
            key={t.id}
            value={t.id}
            className="hover:text-ink data-[state=active]:border-brand-600 data-[state=active]:text-ink -mb-px border-b-2 border-transparent px-4 py-3 text-[15px] font-medium text-slate-600"
          >
            {t.label}
          </T.Trigger>
        ))}
      </T.List>
      {items.map((t) => (
        <T.Content key={t.id} value={t.id} className="pt-8">
          {t.content}
        </T.Content>
      ))}
    </T.Root>
  );
}
