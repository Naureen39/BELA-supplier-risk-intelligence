import type { Metadata } from "next";
import { PageHero, Section } from "@/components/marketing/blocks";
import { ResourceList } from "@/components/marketing/resource-list";
import { ARTICLES, TAGS } from "@/lib/articles";

export const metadata: Metadata = {
  title: "Resources",
  description:
    "Articles on supplier data, entity resolution, public records, and responsible use of risk signals.",
  alternates: { canonical: "/resources" },
};

export default function ResourcesPage() {
  return (
    <>
      <PageHero
        eyebrow="Resources"
        title="Insights on supplier data and risk signals"
        text="Plain explanations of how matching works, what public records mean, and how to measure a system."
      />
      <Section>
        <ResourceList articles={ARTICLES} tags={TAGS} />
      </Section>
    </>
  );
}
