"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api";
import { useAction } from "@/lib/app/hooks";

/** Flag a wrong link or an outdated record. The request goes to the platform review queue. */
export function CorrectionDialog({
  open,
  onOpenChange,
  supplierId,
  eventId,
  companyId,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  supplierId?: string;
  eventId?: number;
  companyId?: number | null;
}) {
  const [kind, setKind] = useState("wrong_link");
  const [text, setText] = useState("");
  const send = useAction(
    () =>
      api("/corrections", {
        json: {
          kind,
          description: text,
          supplier_id: supplierId ?? null,
          event_id: eventId ?? null,
          company_id: companyId ?? null,
        },
      }),
    {
      success: "Correction request sent",
      onDone: () => {
        setText("");
        onOpenChange(false);
      },
    },
  );
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[min(92vw,480px)] -translate-x-1/2 -translate-y-1/2 rounded-[12px] bg-white p-6 shadow-[var(--shadow-3)]">
          <Dialog.Title className="text-ink text-lg font-semibold">
            Request a correction
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-slate-600">
            Tell us what looks wrong. The request is stored and reviewed by the platform team.
          </Dialog.Description>
          <form
            className="mt-4 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              send.mutate(undefined);
            }}
          >
            <Field id="corr-kind" label="What is wrong?">
              {(a) => (
                <Select {...a} value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="wrong_link">A record is linked to the wrong company</option>
                  <option value="outdated_record">A record is out of date</option>
                  <option value="other">Something else</option>
                </Select>
              )}
            </Field>
            <Field id="corr-text" label="Details" hint="Up to 2,000 characters.">
              {(a) => (
                <Textarea
                  {...a}
                  required
                  maxLength={2000}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              )}
            </Field>
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button type="submit" disabled={send.isPending || !text.trim()}>
                Send request
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
