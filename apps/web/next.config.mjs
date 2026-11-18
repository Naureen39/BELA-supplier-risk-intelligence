import createMDX from "@next/mdx";
import createNextIntlPlugin from "next-intl/plugin";

const withMDX = createMDX({});
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const apiOrigin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  pageExtensions: ["ts", "tsx", "md", "mdx"],
  poweredByHeader: false,
  // Compression buffers server-sent events that are proxied from the API. The reverse proxy in front of
  // the site (Caddy) compresses responses instead.
  compress: false,
  images: { formats: ["image/avif", "image/webp"] },
  // The browser talks to one origin; the API is proxied under /api (plan section 10).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
  async headers() {
    const dev = process.env.NODE_ENV !== "production";
    // Next.js writes inline scripts for hydration, so script-src keeps 'unsafe-inline'. A nonce policy would
    // make every page dynamic; see docs/security_review.md for the trade-off.
    const csp = [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self'",
      "connect-src 'self'",
      "worker-src 'self' blob:",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
    ].join("; ");
    const common = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
      { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
      { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    ];
    return [
      // The API sets its own headers (and a different policy for its documentation pages).
      {
        source: "/((?!api/).*)",
        headers: [...common, { key: "Content-Security-Policy", value: csp }],
      },
      { source: "/api/:path*", headers: common },
    ];
  },
};

export default withNextIntl(withMDX(nextConfig));
