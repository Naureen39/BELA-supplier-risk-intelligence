import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { serverApi } from "./api";

export interface SiteStats {
  companies: number;
  facilities: number;
  sources: { source: string; records: number; linked: number; latest: string | null }[];
  evaluation: {
    data: string | null;
    records: number | null;
    config_status: string | null;
    systems: {
      system: string;
      precision: number | null;
      recall: number | null;
      review_rate: number | null;
      false_links_per_1000: number | null;
    }[];
  } | null;
}

type Evaluation = NonNullable<SiteStats["evaluation"]>;

/** The published evaluation file (apps/web/public/metrics.json), used when the API is not reachable. */
async function publishedEvaluation(): Promise<Evaluation | null> {
  try {
    const raw = JSON.parse(
      await readFile(join(process.cwd(), "public", "metrics.json"), "utf8"),
    ) as {
      data: string | null;
      records: number | null;
      config_status: string | null;
      systems: Record<string, Omit<Evaluation["systems"][number], "system">>;
    };
    return {
      data: raw.data,
      records: raw.records,
      config_status: raw.config_status,
      systems: Object.entries(raw.systems).map(([system, m]) => ({ system, ...m })),
    };
  } catch {
    return null;
  }
}

export async function getStats(): Promise<SiteStats | null> {
  const live = await serverApi<SiteStats>("/public/stats");
  if (live?.evaluation) return live;
  const evaluation = await publishedEvaluation();
  if (live) return { ...live, evaluation };
  return evaluation ? { companies: 0, facilities: 0, sources: [], evaluation } : null;
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
