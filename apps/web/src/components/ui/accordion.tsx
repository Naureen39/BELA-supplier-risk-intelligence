"use client";

import * as A from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";

export interface Faq {
  q: string;
  a: string;
}

export function FaqAccordion({ items }: { items: Faq[] }) {
  return (
    <A.Root
      type="single"
      collapsible
      className="divide-line border-line divide-y rounded-[12px] border bg-white"
    >
      {items.map((it, i) => (
        <A.Item key={it.q} value={`item-${i}`}>
          <A.Header>
            <A.Trigger className="group text-ink flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-[16px] font-medium">
              {it.q}
              <ChevronDown
                className="size-5 shrink-0 text-slate-600 transition-transform duration-200 group-data-[state=open]:rotate-180"
                aria-hidden
              />
            </A.Trigger>
          </A.Header>
          <A.Content className="overflow-hidden px-5 pb-5 text-[15px] leading-7 text-slate-700">
            {it.a}
          </A.Content>
        </A.Item>
      ))}
    </A.Root>
  );
}
