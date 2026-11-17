import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { JsonLd } from "@/components/marketing/blocks";
import { Breadcrumbs } from "@/components/ui/breadcrumbs";
import { ARTICLES, renderArticle } from "@/lib/articles";
import { SITE } from "@/lib/site";

export const dynamicParams = false;
export function generateStaticParams() {
  return ARTICLES.map((a) => ({ slug: a.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const a = ARTICLES.find((x) => x.slug === slug);
  if (!a) return {};
  return {
    title: a.title,
    description: a.summary,
    alternates: { canonical: `/resources/${a.slug}` },
    openGraph: { type: "article", title: a.title, description: a.summary, publishedTime: a.date },
  };
}

export default async function ArticlePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const a = ARTICLES.find((x) => x.slug === slug);
  const body = renderArticle(slug);
  if (!a || !body) notFound();
  const more = ARTICLES.filter((x) => x.slug !== slug).slice(0, 3);
  return (
    <article>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Article",
          headline: a.title,
          description: a.summary,
          datePublished: a.date,
          author: { "@type": "Organization", name: SITE.name },
          publisher: { "@type": "Organization", name: SITE.name },
          mainEntityOfPage: `${SITE.url}/resources/${a.slug}`,
        }}
      />
      <header className="border-line border-b bg-white py-12 lg:py-16">
        <div className="container-page">
          <div className="mx-auto max-w-3xl">
            <Breadcrumbs items={[{ title: "Resources", href: "/resources" }, { title: a.tag }]} />
            <h1 className="text-h1 mt-5">{a.title}</h1>
            <p className="mt-4 text-lg leading-8 text-slate-700">{a.summary}</p>
            <p className="mt-4 text-sm text-slate-600">
              <time dateTime={a.date}>
                {new Date(a.date).toLocaleDateString("en-US", {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                  timeZone: "UTC",
                })}
              </time>{" "}
              &middot; {a.readMinutes} min read
            </p>
          </div>
        </div>
      </header>
      <div className="container-page py-12">
        <div className="mx-auto max-w-3xl">
          {body}
          <p className="bg-brand-100 mt-12 rounded-[12px] p-4 text-sm text-slate-700">
            {SITE.disclaimer}
          </p>
        </div>
      </div>
      <section className="border-line border-t bg-white py-12">
        <div className="container-page">
          <div className="content-width">
            <h2 className="text-h3 mb-6">More articles</h2>
            <ul className="grid gap-4 md:grid-cols-3">
              {more.map((m) => (
                <li key={m.slug}>
                  <Link
                    href={`/resources/${m.slug}`}
                    className="border-line block rounded-[12px] border p-5 hover:bg-slate-50"
                  >
                    <span className="text-brand-600 text-xs font-medium tracking-wider uppercase">
                      {m.tag}
                    </span>
                    <span className="text-ink mt-1 block font-medium">{m.title}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </article>
  );
}
