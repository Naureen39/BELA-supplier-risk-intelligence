import { useTranslations } from "next-intl";
import Link from "next/link";
import { Wordmark } from "@/components/art/logo";
import { COMPANY_NAV, INDUSTRY_NAV, PLATFORM_NAV, RESOURCES_NAV, SOLUTIONS_NAV } from "@/lib/site";
import { NewsletterForm } from "./newsletter-form";

function Col({ title, links }: { title: string; links: { title: string; href: string }[] }) {
  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold text-white">{title}</h2>
      <ul className="space-y-2">
        {links.map((l) => (
          <li key={l.href}>
            <Link href={l.href} className="text-sm text-slate-300 hover:text-white">
              {l.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Footer() {
  const t = useTranslations("footer");
  const n = useTranslations("nav");
  return (
    <footer className="bg-ink text-slate-300">
      <div className="container-page py-14">
        <div className="grid gap-10 lg:grid-cols-[1.1fr_2fr]">
          <div className="space-y-6">
            <Wordmark light />
            <NewsletterForm />
          </div>
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:grid-cols-5">
            <Col title={n("platform")} links={PLATFORM_NAV} />
            <Col title={n("solutions")} links={SOLUTIONS_NAV} />
            <Col title={n("industries")} links={INDUSTRY_NAV} />
            <Col title={n("resources")} links={RESOURCES_NAV} />
            <Col title={n("company")} links={COMPANY_NAV} />
          </div>
        </div>
        <div className="mt-12 space-y-3 border-t border-slate-700 pt-6 text-sm">
          <p className="font-medium text-white">{t("disclaimer")}</p>
          <p>{t("credits")}</p>
          <p>
            &copy; {new Date().getFullYear()} Provenance Risk. Demonstration product.{" "}
            <Link href="/legal/privacy" className="underline">
              {t("privacy")}
            </Link>{" "}
            <Link href="/legal/terms" className="underline">
              {t("terms")}
            </Link>{" "}
            <Link href="/legal/cookies" className="underline">
              {t("cookies")}
            </Link>
          </p>
        </div>
      </div>
    </footer>
  );
}
