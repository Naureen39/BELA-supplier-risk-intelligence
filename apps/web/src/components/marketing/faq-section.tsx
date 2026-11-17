import { FaqAccordion, type Faq } from "@/components/ui/accordion";
import { JsonLd, Section, SectionHead } from "./blocks";

export function FaqSection({
  items,
  title = "Frequently asked questions",
}: {
  items: Faq[];
  title?: string;
}) {
  return (
    <Section tone="white">
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "FAQPage",
          mainEntity: items.map((i) => ({
            "@type": "Question",
            name: i.q,
            acceptedAnswer: { "@type": "Answer", text: i.a },
          })),
        }}
      />
      <SectionHead title={title} />
      <div className="max-w-3xl">
        <FaqAccordion items={items} />
      </div>
    </Section>
  );
}
