"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { api, ApiRequestError } from "@/lib/api";

export function NewsletterForm() {
  const t = useTranslations("footer");
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("busy");
    try {
      const r = await api<{ detail: string }>("/newsletter", { json: { email } });
      setMessage(r.detail);
      setState("done");
    } catch (err) {
      setMessage(
        err instanceof ApiRequestError && err.status === 429
          ? "Too many requests. Try again later."
          : "Enter a valid email address.",
      );
      setState("error");
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2" noValidate>
      <label htmlFor="nl-email" className="block text-sm font-medium text-white">
        {t("newsletter")}
      </label>
      <p className="text-sm text-slate-300">{t("newsletterHint")}</p>
      <div className="flex gap-2">
        <Input
          id="nl-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t("email")}
          className="h-10 border-slate-600 bg-slate-900 text-white placeholder:text-slate-400"
        />
        <Button type="submit" size="sm" className="h-10 shrink-0" disabled={state === "busy"}>
          {t("subscribe")}
        </Button>
      </div>
      <p
        role="status"
        className={`text-sm ${state === "error" ? "text-[#ff9b8f]" : "text-slate-300"}`}
      >
        {state === "done" || state === "error" ? message : ""}
      </p>
    </form>
  );
}
