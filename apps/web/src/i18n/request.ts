import { getRequestConfig } from "next-intl/server";

// One locale is served today. Message files for es, fr, and de hold the shell strings so that a
// locale-prefixed route tree can be added without touching components (see docs/web.md).
export default getRequestConfig(async () => {
  const locale = "en";
  return { locale, messages: (await import(`../../messages/${locale}.json`)).default };
});
