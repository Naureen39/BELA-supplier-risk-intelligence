import Link from "next/link";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function Section({
  id,
  children,
  className,
  tone = "page",
}: {
  id?: string;
  children: ReactNode;
  className?: string;
  tone?: "page" | "white" | "ink";
}) {
  return (
    <section
      id={id}
      className={cn(
        "section-pad scroll-mt-24",
        tone === "white" && "bg-white",
        tone === "ink" && "bg-ink text-slate-200",
        className,
      )}
    >
      <div className="container-page">
        <div className="content-width">{children}</div>
      </div>
    </section>
  );
}

export function Eyebrow({ children, dark = false }: { children: ReactNode; dark?: boolean }) {
  return (
    <p
      className={cn(
        "mb-3 text-sm font-semibold tracking-wider uppercase",
        dark ? "text-teal" : "text-brand-600",
      )}
    >
      {children}
    </p>
  );
}

export function SectionHead({
  eyebrow,
  title,
  text,
  dark = false,
}: {
  eyebrow?: string;
  title: string;
  text?: string;
  dark?: boolean;
}) {
  return (
    <div className="mb-10 max-w-2xl lg:mb-14">
      {eyebrow && <Eyebrow dark={dark}>{eyebrow}</Eyebrow>}
      <h2 className={dark ? "text-h2 text-white" : "text-h2"}>{title}</h2>
      {text && (
        <p className={cn("mt-4 text-[17px] leading-8", dark ? "text-slate-300" : "text-slate-700")}>
          {text}
        </p>
      )}
    </div>
  );
}

export function PageHero({
  eyebrow,
  title,
  text,
  children,
}: {
  eyebrow?: string;
  title: string;
  text?: string;
  children?: ReactNode;
}) {
  return (
    <section className="border-line border-b bg-white pt-14 pb-14 lg:pt-20 lg:pb-20">
      <div className="container-page">
        <div className="content-width">
          {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
          <h1 className="text-h1 max-w-3xl">{title}</h1>
          {text && <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-700">{text}</p>}
          {children && <div className="mt-8">{children}</div>}
        </div>
      </div>
    </section>
  );
}

export function CtaBand() {
  return (
    <section className="bg-navy py-16 text-white">
      <div className="container-page">
        <div className="content-width flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-center">
          <div className="max-w-xl">
            <h2 className="text-h2 text-white">See it on a supplier list like yours</h2>
            <p className="mt-3 text-slate-300">
              Request a demonstration and we will walk through resolution, review, and monitoring
              with demo data.
            </p>
          </div>
          <Button asChild size="lg" className="text-ink bg-white hover:bg-slate-100">
            <Link href="/contact">Request a demo</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}

export function JsonLd({ data }: { data: Record<string, unknown> }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }}
    />
  );
}
