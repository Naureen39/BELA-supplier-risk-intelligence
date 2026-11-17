declare module "*.mdx" {
  import type { ComponentType } from "react";
  export const meta: {
    slug: string;
    title: string;
    summary: string;
    tag: string;
    date: string;
    readMinutes: number;
  };
  const MDXContent: ComponentType;
  export default MDXContent;
}
