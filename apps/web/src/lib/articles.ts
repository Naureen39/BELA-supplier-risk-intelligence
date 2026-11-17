import { createElement, type ComponentType, type ReactElement } from "react";
import * as a1 from "@/content/articles/why-supplier-names-never-match.mdx";
import * as a2 from "@/content/articles/from-facility-to-parent.mdx";
import * as a3 from "@/content/articles/entity-resolution-in-practice.mdx";
import * as a4 from "@/content/articles/what-regulator-data-can-and-cannot-tell-you.mdx";
import * as a5 from "@/content/articles/measuring-a-matching-system.mdx";
import * as a6 from "@/content/articles/responsible-use-of-risk-signals.mdx";

export interface ArticleMeta {
  slug: string;
  title: string;
  summary: string;
  tag: string;
  date: string;
  readMinutes: number;
}

interface MdxModule {
  meta: ArticleMeta;
  default: ComponentType;
}

const MODULES = [a1, a2, a3, a4, a5, a6] as unknown as MdxModule[];

/** Newest first. */
export const ARTICLES: ArticleMeta[] = MODULES.map((m) => m.meta).sort((a, b) =>
  b.date.localeCompare(a.date),
);

export function renderArticle(slug: string): ReactElement | null {
  const mod = MODULES.find((m) => m.meta.slug === slug);
  return mod ? createElement(mod.default) : null;
}

export const TAGS = Array.from(new Set(ARTICLES.map((a) => a.tag))).sort();
