import type { Metadata } from "next";
import Link from "next/link";
import { PageHero, Section } from "@/components/marketing/blocks";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Request received", robots: { index: false } };

export default function ThanksPage() {
  return (
    <>
      <PageHero eyebrow="Contact" title="Thank you. We will contact you by email." />
      <Section>
        <p className="max-w-xl text-[17px] leading-8 text-slate-700">
          Your request has been stored. In the meantime, read how matching is measured or return to
          the home page.
        </p>
        <div className="mt-6 flex gap-3">
          <Button asChild>
            <Link href="/methodology">Read the methodology</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/">Home</Link>
          </Button>
        </div>
      </Section>
    </>
  );
}
