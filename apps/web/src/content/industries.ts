import type { IconName } from "@/lib/site";

export interface Industry {
  slug: string;
  name: string;
  icon: IconName;
  tint: [string, string];
  card: string;
  intro: string;
  themes: { title: string; text: string; source: string }[];
  scenario: { title: string; text: string };
  workflow: string[];
  related: { title: string; href: string }[];
  faq: { q: string; a: string }[];
}

const COMMON_FAQ = [
  {
    q: "Does a record mean the supplier did something wrong?",
    a: "No. A citation, inspection result, or recall is a public record with its own status. The product shows what the record says, the source, and the date. It does not state fault.",
  },
  {
    q: "How current is the data?",
    a: "Each source has its own publication schedule. The data coverage page lists the latest record date per source, and every event shows the date the record was reported.",
  },
  {
    q: "Can we use our own supplier identifiers?",
    a: "Yes. Upload columns for your own identifiers are kept and returned in exports next to the canonical company.",
  },
];

export const INDUSTRIES: Industry[] = [
  {
    slug: "manufacturing",
    name: "Manufacturing",
    icon: "factory",
    tint: ["#12305A", "#2F74D8"],
    card: "Plant-level safety and environmental records, rolled up to the company you buy from.",
    intro:
      "Manufacturers buy from plants, and public records are filed against plants. Linking a plant to its operator and parent shows which suppliers share exposure.",
    themes: [
      {
        title: "Workplace safety inspections",
        text: "Inspection and citation records filed against an establishment, with penalty amounts and case status.",
        source: "OSHA inspection data (US Department of Labor)",
      },
      {
        title: "Environmental compliance",
        text: "Facility compliance status and enforcement history under US environmental programs.",
        source: "EPA ECHO",
      },
      {
        title: "Plant closures and disruptions",
        text: "News reports of fires, outages, and closures at named sites.",
        source: "News articles (metadata and snippets)",
      },
    ],
    scenario: {
      title: "A plant record under a shared parent",
      text: "A buyer lists two component suppliers with different names. The corporate family shows both are subsidiaries of one parent. A workplace safety record at one plant is then relevant to both lines of supply. All names in this scenario are fictional.",
    },
    workflow: [
      "Upload the supplier list with plant locations.",
      "Review facility-level matches the model is unsure about.",
      "Check the corporate family for shared parents.",
      "Set an alert rule for workplace safety events at severity three or higher.",
    ],
    related: [
      { title: "Corporate family mapping", href: "/platform#family" },
      { title: "Risk scoring", href: "/platform#risk" },
    ],
  },
  {
    slug: "automotive",
    name: "Automotive",
    icon: "car",
    tint: ["#0B1B33", "#1F5FBF"],
    card: "Vehicle and equipment recall exposure across tiers of suppliers.",
    intro:
      "Recalls name a manufacturer, a component, and a unit count. Resolving the manufacturer to a canonical company connects the recall to the suppliers in your list.",
    themes: [
      {
        title: "Vehicle and equipment recalls",
        text: "Recall campaigns with the manufacturer, component, and number of units potentially affected.",
        source: "NHTSA recalls",
      },
      {
        title: "Plant safety",
        text: "Establishment inspections at assembly and parts plants.",
        source: "OSHA inspection data",
      },
      {
        title: "Ownership changes",
        text: "Parent and subsidiary relationships that change which supplier a record belongs to.",
        source: "SEC Exhibit 21, GLEIF",
      },
    ],
    scenario: {
      title: "A recall at a brand, not a supplier",
      text: "A recall names a brand that your supplier list records under a legal entity name. Resolution links the brand to the legal entity and its parent, so the recall appears on the right supplier. The brand and entities are fictional.",
    },
    workflow: [
      "Upload suppliers with legal names and states.",
      "Accept high-confidence matches in bulk and review the rest.",
      "Read the recall record and its unit count on the supplier profile.",
      "Export the resolved list with canonical identifiers for your own systems.",
    ],
    related: [
      { title: "Events", href: "/platform#events" },
      { title: "Entity resolution", href: "/platform#resolution" },
    ],
  },
  {
    slug: "food-and-beverage",
    name: "Food and beverage",
    icon: "utensils",
    tint: ["#1E8E5A", "#00A3A3"],
    card: "Food safety enforcement and recall records linked to processors and brands.",
    intro:
      "Food supply chains pair brands with processing plants. Enforcement records identify firms by name and location, which makes careful matching essential.",
    themes: [
      {
        title: "Food and drug enforcement reports",
        text: "Recall classifications, product descriptions, and the recalling firm.",
        source: "openFDA enforcement",
      },
      {
        title: "Processing plant safety",
        text: "Workplace inspections at plants and warehouses.",
        source: "OSHA inspection data",
      },
      {
        title: "Environmental releases",
        text: "Discharge and compliance records for facilities.",
        source: "EPA ECHO",
      },
    ],
    scenario: {
      title: "Two plants with the same name",
      text: "Two facilities share a name in different states. A recall record carries only the firm name and a city. Resolution uses the state and city to pick the right company and leaves ambiguous records in review. Names are fictional.",
    },
    workflow: [
      "Upload suppliers with city and state.",
      "Review records where two companies share a name.",
      "Monitor for recall classifications you care about.",
      "Share a PDF supplier report with quality teams.",
    ],
    related: [
      { title: "Review workflow", href: "/platform#resolution" },
      { title: "Monitoring", href: "/platform#monitoring" },
    ],
  },
  {
    slug: "consumer-products",
    name: "Consumer products",
    icon: "package",
    tint: ["#8E5BD9", "#2F74D8"],
    card: "Product safety recalls across brands, importers, and manufacturers.",
    intro:
      "Consumer product recalls list manufacturers, importers, distributors, and retailers. A single recall can touch several companies in a supply base.",
    themes: [
      {
        title: "Product safety recalls",
        text: "Recall notices with the hazard, units, and the companies named.",
        source: "CPSC recalls",
      },
      {
        title: "Plant and warehouse safety",
        text: "Inspection records at manufacturing and distribution sites.",
        source: "OSHA inspection data",
      },
      {
        title: "News coverage of defects",
        text: "Reports of product defects and lawsuits that name a company.",
        source: "News articles (metadata and snippets)",
      },
    ],
    scenario: {
      title: "A recall that names an importer",
      text: "A recall lists an importer and a manufacturer. The product links both to canonical companies and shows each role. A buyer sees which of their suppliers appear and in what role. All names are fictional.",
    },
    workflow: [
      "Upload brands and legal entities together.",
      "Check roles on each event (manufacturer, importer, retailer).",
      "Set a rule for recalls with a high hazard class.",
      "Review the corporate family for shared importers.",
    ],
    related: [
      { title: "Events", href: "/platform#events" },
      { title: "Corporate family", href: "/platform#family" },
    ],
  },
  {
    slug: "healthcare-and-life-sciences",
    name: "Healthcare and life sciences",
    icon: "flask",
    tint: ["#00A3A3", "#12305A"],
    card: "Drug and device enforcement records for manufacturers and contract partners.",
    intro:
      "Regulated manufacturing creates detailed public records. Linking them to the right legal entity matters when a contract manufacturer shares a site name with another firm.",
    themes: [
      {
        title: "Drug and device enforcement",
        text: "Enforcement reports with classification, reason, and the responsible firm.",
        source: "openFDA enforcement",
      },
      {
        title: "Facility safety",
        text: "Workplace inspections at laboratories and plants.",
        source: "OSHA inspection data",
      },
      {
        title: "Corporate transactions",
        text: "Acquisitions that move a facility from one parent to another.",
        source: "SEC Exhibit 21, GLEIF, Wikidata",
      },
    ],
    scenario: {
      title: "A contract manufacturer after an acquisition",
      text: "A contract manufacturer is acquired. Older records name the former owner. The family graph shows the as-of date of each ownership edge so reviewers can read older records in context. Names are fictional.",
    },
    workflow: [
      "Upload suppliers with site addresses.",
      "Read the as-of date on each ownership edge.",
      "Review enforcement records with the reviewer notes.",
      "Export evidence for the quality file.",
    ],
    related: [
      { title: "Corporate family", href: "/platform#family" },
      { title: "Methodology", href: "/methodology" },
    ],
  },
  {
    slug: "logistics",
    name: "Logistics",
    icon: "truck",
    tint: ["#12305A", "#00A3A3"],
    card: "Carrier and warehouse safety signals for the network you rely on.",
    intro:
      "Logistics networks mix large carriers with small operators. Public records exist for some of them, and names rarely match across systems.",
    themes: [
      {
        title: "Warehouse and dock safety",
        text: "Inspection and citation records for facilities.",
        source: "OSHA inspection data",
      },
      {
        title: "Equipment and vehicle recalls",
        text: "Recalls that affect fleets and equipment.",
        source: "NHTSA recalls",
      },
      {
        title: "Operational disruption",
        text: "News of strikes, closures, and incidents at named sites.",
        source: "News articles (metadata and snippets)",
      },
    ],
    scenario: {
      title: "A regional operator inside a larger group",
      text: "A regional carrier is part of a larger group. A news report names the group. Resolution links the report to the group and the roll-up reaches the regional carrier with a lower weight than a direct record. Names are fictional.",
    },
    workflow: [
      "Upload carriers and warehouse operators.",
      "Review the carriers that resolve to a group.",
      "Check concentration: how many suppliers sit under one parent.",
      "Set webhook alerts for your operations team.",
    ],
    related: [
      { title: "Monitoring", href: "/platform#monitoring" },
      { title: "API", href: "/developers" },
    ],
  },
].map((i) => ({ ...i, faq: COMMON_FAQ })) as Industry[];

export const bySlug = (slug: string): Industry | undefined =>
  INDUSTRIES.find((i) => i.slug === slug);
