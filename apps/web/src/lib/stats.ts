import { serverApi } from "./api";

export interface SiteStats {
  companies: number;
  facilities: number;
  sources: { source: string; records: number; linked: number; latest: string | null }[];
  evaluation: {
    data: string | null;
    records: number | null;
    config_status: string | null;
    systems: { system: string; precision: number | null; false_links_per_1000: number | null }[];
  } | null;
}

export async function getStats(): Promise<SiteStats | null> {
  return serverApi<SiteStats>("/public/stats");
}

export const SOURCE_LABELS: Record<string, string> = {
  epa_echo: "EPA ECHO",
  osha: "OSHA",
  nhtsa: "NHTSA",
  cpsc: "CPSC",
  openfda: "FDA (openFDA)",
  news: "News (GDELT)",
};

export function fmt(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}
