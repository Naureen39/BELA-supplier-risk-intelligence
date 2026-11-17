import type { MetadataRoute } from "next";
import { INDUSTRIES } from "@/content/industries";
import { LEGAL } from "@/content/legal";
import { SOLUTIONS } from "@/content/solutions";
import { ARTICLES } from "@/lib/articles";
import { SITE } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const fixed = [
    "",
    "/platform",
    "/pricing",
    "/security",
    "/developers",
    "/methodology",
    "/resources",
    "/company",
    "/contact",
  ];
  const urls = [
    ...fixed,
    ...SOLUTIONS.map((s) => `/solutions/${s.slug}`),
    ...INDUSTRIES.map((i) => `/industries/${i.slug}`),
    ...LEGAL.map((d) => `/legal/${d.slug}`),
    ...ARTICLES.map((a) => `/resources/${a.slug}`),
  ];
  return urls.map((u) => ({
    url: `${SITE.url}${u}`,
    changeFrequency: "monthly",
    priority: u === "" ? 1 : 0.6,
  }));
}
