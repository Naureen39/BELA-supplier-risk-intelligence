"use client";

import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

export function Drawer({
  open,
  onOpenChange,
  title,
  closeLabel,
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  closeLabel: string;
  children: ReactNode;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="bg-ink/40 fixed inset-0 z-50" />
        <D.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(92vw,380px)] flex-col overflow-y-auto bg-white p-6 shadow-[var(--shadow-3)]">
          <div className="flex items-center justify-between">
            <D.Title className="text-ink text-lg font-semibold">{title}</D.Title>
            <D.Close className="rounded-[8px] p-2 hover:bg-slate-100" aria-label={closeLabel}>
              <X className="size-5" aria-hidden />
            </D.Close>
          </div>
          <D.Description className="sr-only">{title}</D.Description>
          {children}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
