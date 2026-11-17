import { getTranslations } from "next-intl/server";
import { CookieNotice } from "@/components/marketing/cookie-notice";
import { Footer } from "@/components/marketing/footer";
import { Header } from "@/components/marketing/header";
import { UtilityBar } from "@/components/marketing/utility-bar";

export default async function MarketingLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("nav");
  return (
    <>
      <a
        href="#main"
        className="focus:text-ink sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[60] focus:rounded-[8px] focus:bg-white focus:px-4 focus:py-2 focus:shadow-[var(--shadow-3)]"
      >
        {t("skip")}
      </a>
      <UtilityBar />
      <Header />
      <main id="main">{children}</main>
      <Footer />
      <CookieNotice />
    </>
  );
}
