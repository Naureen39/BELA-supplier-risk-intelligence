import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/app", "/login", "/forgot-password", "/reset-password", "/api/"],
      },
    ],
    sitemap: `${SITE.url}/sitemap.xml`,
  };
}
