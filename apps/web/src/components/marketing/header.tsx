"use client";

import * as NM from "@radix-ui/react-navigation-menu";
import { ChevronDown, Menu } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@/components/art/icon";
import { Wordmark } from "@/components/art/logo";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { cn } from "@/lib/cn";
import {
  COMPANY_NAV,
  INDUSTRY_NAV,
  PLATFORM_NAV,
  RESOURCES_NAV,
  SOLUTIONS_NAV,
  type NavItem,
} from "@/lib/site";

const triggerCls =
  "group inline-flex h-10 items-center gap-1 rounded-[8px] px-3 text-[15px] font-medium text-ink hover:bg-slate-100 data-[state=open]:bg-slate-100";

function Mega({
  items,
  featured,
}: {
  items: NavItem[];
  featured: { title: string; text: string; href: string };
}) {
  return (
    <div className="grid w-[min(900px,92vw)] grid-cols-[1fr_260px] gap-6 p-6">
      <ul className="grid grid-cols-2 gap-1">
        {items.map((it) => (
          <li key={it.href}>
            <NM.Link asChild>
              <Link href={it.href} className="flex gap-3 rounded-[10px] p-3 hover:bg-slate-50">
                <span className="bg-brand-100 text-brand-600 mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-[8px]">
                  <Icon name={it.icon} className="size-5" />
                </span>
                <span>
                  <span className="text-ink block text-[15px] font-medium">{it.title}</span>
                  <span className="block text-sm leading-5 text-slate-600">{it.description}</span>
                </span>
              </Link>
            </NM.Link>
          </li>
        ))}
      </ul>
      <NM.Link asChild>
        <Link
          href={featured.href}
          className="bg-navy flex flex-col justify-end rounded-[12px] p-5 text-white hover:bg-[#0f2a50]"
        >
          <span className="text-xs font-medium tracking-wider text-slate-300 uppercase">
            Featured
          </span>
          <span className="mt-2 text-lg font-semibold">{featured.title}</span>
          <span className="mt-1 text-sm leading-5 text-slate-300">{featured.text}</span>
        </Link>
      </NM.Link>
    </div>
  );
}

export function Header() {
  const t = useTranslations("nav");
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-40 h-[72px] border-b transition-colors duration-200",
        scrolled ? "border-line bg-white/80 backdrop-blur-md" : "bg-page border-transparent",
      )}
    >
      <div className="container-page flex h-full items-center justify-between gap-6">
        <Link href="/" aria-label="Provenance Risk home" className="shrink-0">
          <Wordmark />
        </Link>

        <NM.Root className="relative hidden xl:block" aria-label="Main">
          <NM.List className="flex items-center gap-1">
            <NM.Item>
              <NM.Trigger className={triggerCls}>
                {t("platform")}
                <ChevronDown
                  className="size-4 transition-transform group-data-[state=open]:rotate-180"
                  aria-hidden
                />
              </NM.Trigger>
              <NM.Content className="absolute top-full left-0 pt-2">
                <div className="border-line rounded-[12px] border bg-white shadow-[var(--shadow-3)]">
                  <Mega
                    items={PLATFORM_NAV}
                    featured={{
                      title: "How matching is measured",
                      text: "Read the evaluation design and the known limits.",
                      href: "/methodology",
                    }}
                  />
                </div>
              </NM.Content>
            </NM.Item>
            <NM.Item>
              <NM.Trigger className={triggerCls}>
                {t("solutions")}
                <ChevronDown
                  className="size-4 transition-transform group-data-[state=open]:rotate-180"
                  aria-hidden
                />
              </NM.Trigger>
              <NM.Content className="absolute top-full left-0 pt-2">
                <div className="border-line rounded-[12px] border bg-white shadow-[var(--shadow-3)]">
                  <Mega
                    items={SOLUTIONS_NAV}
                    featured={{
                      title: "Responsible use of risk signals",
                      text: "Records are not verdicts. See how the product frames them.",
                      href: "/resources/responsible-use-of-risk-signals",
                    }}
                  />
                </div>
              </NM.Content>
            </NM.Item>
            <NM.Item>
              <NM.Trigger className={triggerCls}>
                {t("industries")}
                <ChevronDown
                  className="size-4 transition-transform group-data-[state=open]:rotate-180"
                  aria-hidden
                />
              </NM.Trigger>
              <NM.Content className="absolute top-full left-0 pt-2">
                <div className="border-line rounded-[12px] border bg-white shadow-[var(--shadow-3)]">
                  <Mega
                    items={INDUSTRY_NAV}
                    featured={{
                      title: "What recall and enforcement data can tell you",
                      text: "And what it cannot.",
                      href: "/resources/what-regulator-data-can-and-cannot-tell-you",
                    }}
                  />
                </div>
              </NM.Content>
            </NM.Item>
            <NM.Item>
              <NM.Link asChild>
                <Link href="/resources" className={triggerCls}>
                  {t("resources")}
                </Link>
              </NM.Link>
            </NM.Item>
            <NM.Item>
              <NM.Link asChild>
                <Link href="/pricing" className={triggerCls}>
                  {t("pricing")}
                </Link>
              </NM.Link>
            </NM.Item>
            <NM.Item>
              <NM.Link asChild>
                <Link href="/company" className={triggerCls}>
                  {t("company")}
                </Link>
              </NM.Link>
            </NM.Item>
          </NM.List>
        </NM.Root>

        <div className="hidden items-center gap-2 xl:flex">
          <Link
            href="/login"
            className="text-ink rounded-[8px] px-3 py-2 text-[15px] font-medium hover:bg-slate-100"
          >
            {t("login")}
          </Link>
          <Button asChild>
            <Link href="/contact">{t("demo")}</Link>
          </Button>
        </div>

        <button
          type="button"
          className="rounded-[8px] p-2 hover:bg-slate-100 xl:hidden"
          aria-label={t("menu")}
          onClick={() => setOpen(true)}
        >
          <Menu className="size-6" aria-hidden />
        </button>
      </div>

      <Drawer open={open} onOpenChange={setOpen} title={t("menu")} closeLabel={t("close")}>
        <nav aria-label="Mobile" className="mt-6 space-y-6">
          {[
            [t("platform"), PLATFORM_NAV.map((i) => ({ title: i.title, href: i.href }))],
            [t("solutions"), SOLUTIONS_NAV.map((i) => ({ title: i.title, href: i.href }))],
            [t("industries"), INDUSTRY_NAV.map((i) => ({ title: i.title, href: i.href }))],
            [t("resources"), RESOURCES_NAV],
            [t("company"), [{ title: t("pricing"), href: "/pricing" }, ...COMPANY_NAV.slice(0, 2)]],
          ].map(([heading, links]) => (
            <div key={heading as string}>
              <p className="mb-2 text-xs font-semibold tracking-wider text-slate-600 uppercase">
                {heading as string}
              </p>
              <ul className="space-y-1">
                {(links as { title: string; href: string }[]).map((l) => (
                  <li key={l.href}>
                    <Link
                      href={l.href}
                      onClick={() => setOpen(false)}
                      className="text-ink block rounded-[8px] px-2 py-2 text-[15px] hover:bg-slate-100"
                    >
                      {l.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="mt-8 flex flex-col gap-3">
          <Button asChild variant="secondary">
            <Link href="/login" onClick={() => setOpen(false)}>
              {t("login")}
            </Link>
          </Button>
          <Button asChild>
            <Link href="/contact" onClick={() => setOpen(false)}>
              {t("demo")}
            </Link>
          </Button>
        </div>
      </Drawer>
    </header>
  );
}
