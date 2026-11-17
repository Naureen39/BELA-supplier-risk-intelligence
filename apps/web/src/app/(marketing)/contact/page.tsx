import type { Metadata } from "next";
import { Suspense } from "react";
import { PageHero, Section } from "@/components/marketing/blocks";
import { ContactForm } from "@/components/marketing/contact-form";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "Request a demo",
  description: "Request a demonstration of supplier resolution, review, and monitoring.",
  alternates: { canonical: "/contact" },
};

export default function ContactPage() {
  return (
    <>
      <PageHero
        eyebrow="Contact"
        title="Request a demonstration"
        text="Tell us a little about your supplier list. We will reply by email."
      />
      <Section>
        <div className="max-w-2xl">
          <Suspense fallback={<Skeleton className="h-96 w-full" />}>
            <ContactForm />
          </Suspense>
        </div>
      </Section>
    </>
  );
}
