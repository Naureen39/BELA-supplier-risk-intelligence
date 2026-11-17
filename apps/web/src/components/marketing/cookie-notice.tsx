"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";

const KEY = "pr_cookie_notice";
const EVENT = "pr-cookie-notice";

function subscribe(cb: () => void): () => void {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

function dismissed(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function CookieNotice() {
  const t = useTranslations("cookie");
  // Hidden on the server and during hydration, so the page never shifts when the notice resolves.
  const hidden = useSyncExternalStore(subscribe, dismissed, () => true);
  if (hidden) return null;
  return (
    <div
      role="region"
      aria-label="Cookie notice"
      className="border-line fixed inset-x-4 bottom-4 z-50 mx-auto max-w-3xl rounded-[12px] border bg-white p-4 shadow-[var(--shadow-3)] sm:flex sm:items-center sm:gap-4"
    >
      <p className="text-sm leading-6 text-slate-700">
        {t("text")}{" "}
        <Link href="/legal/cookies" className="text-brand-600 underline underline-offset-2">
          {t("more")}
        </Link>
      </p>
      <Button
        size="sm"
        className="mt-3 sm:mt-0"
        onClick={() => {
          try {
            localStorage.setItem(KEY, "1");
          } catch {
            /* storage unavailable: the notice returns on the next visit */
          }
          window.dispatchEvent(new Event(EVENT));
        }}
      >
        {t("ok")}
      </Button>
    </div>
  );
}
