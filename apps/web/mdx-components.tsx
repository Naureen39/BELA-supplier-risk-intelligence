import type { MDXComponents } from "mdx/types";
import Link from "next/link";

export function useMDXComponents(components: MDXComponents): MDXComponents {
  return {
    h2: (p) => <h2 className="text-ink mt-12 mb-4 text-2xl font-semibold tracking-tight" {...p} />,
    h3: (p) => <h3 className="text-ink mt-8 mb-3 text-xl font-semibold" {...p} />,
    p: (p) => <p className="my-4 text-[17px] leading-8 text-slate-700" {...p} />,
    ul: (p) => (
      <ul className="my-4 list-disc space-y-2 pl-6 text-[17px] leading-8 text-slate-700" {...p} />
    ),
    ol: (p) => (
      <ol
        className="my-4 list-decimal space-y-2 pl-6 text-[17px] leading-8 text-slate-700"
        {...p}
      />
    ),
    a: ({ href = "#", ...rest }) => (
      <Link
        href={href}
        className="text-brand-600 hover:text-brand-500 underline underline-offset-4"
        {...rest}
      />
    ),
    blockquote: (p) => (
      <blockquote
        className="border-brand-500 bg-brand-100/60 my-6 border-l-4 px-5 py-3 text-slate-700"
        {...p}
      />
    ),
    table: (p) => (
      <div
        className="my-6 overflow-x-auto"
        tabIndex={0}
        role="region"
        aria-label="Table, scrolls horizontally on small screens"
      >
        <table className="w-full border-collapse text-left text-[15px]" {...p} />
      </div>
    ),
    th: (p) => (
      <th className="border-line text-ink border-b bg-slate-50 px-3 py-2 font-semibold" {...p} />
    ),
    td: (p) => <td className="border-line border-b px-3 py-2 text-slate-700" {...p} />,
    code: (p) => (
      <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em]" {...p} />
    ),
    ...components,
  };
}
