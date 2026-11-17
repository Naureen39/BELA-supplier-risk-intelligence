"use client";

import { Globe } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

const LANGS = [
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
];

export function UtilityBar() {
  const t = useTranslations("utility");
  return (
    <aside aria-label="Utility" className="bg-ink h-10 text-sm text-slate-200">
      <div className="container-page flex h-full items-center justify-between">
        <p className="hidden truncate sm:block">
          Demo environment. Revenue, usage, and portfolio figures are demo data.
        </p>
        <ul className="ml-auto flex items-center gap-4 sm:gap-5">
          <li className="hidden sm:list-item">
            <Link href="/contact" className="hover:text-white">
              {t("support")}
            </Link>
          </li>
          <li className="hidden sm:list-item">
            <a href="/api/v1/health/ready" className="hover:text-white">
              {t("status")}
            </a>
          </li>
          <li>
            <Link href="/developers" className="hover:text-white">
              {t("developers")}
            </Link>
          </li>
          <li className="flex items-center gap-1.5">
            <Globe className="size-4" aria-hidden />
            <label htmlFor="lang" className="sr-only">
              {t("language")}
            </label>
            <select
              id="lang"
              defaultValue="en"
              className="bg-ink focus-visible:outline-brand-500 rounded py-0.5 text-sm text-slate-200"
              onChange={(e) => {
                e.currentTarget.value = "en";
              }}
              title={t("unavailable")}
            >
              {LANGS.map((l) => (
                <option key={l.code} value={l.code} disabled={l.code !== "en"}>
                  {l.label}
                  {l.code !== "en" ? " (soon)" : ""}
                </option>
              ))}
            </select>
          </li>
        </ul>
      </div>
    </aside>
  );
}
