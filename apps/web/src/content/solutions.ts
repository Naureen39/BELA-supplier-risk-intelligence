export interface Solution {
  slug: string;
  name: string;
  headline: string;
  problem: string;
  approach: string[];
  workflow: string[];
  measures: { metric: string; text: string }[];
  faq: { q: string; a: string }[];
}

const MEASURES = [
  {
    metric: "Precision of automatic matches",
    text: "The share of automatically accepted matches that are correct on the gold set. Reported on the methodology page with the data it was computed on.",
  },
  {
    metric: "False links per 1,000 records",
    text: "Wrong company attached to a record, compared with a fuzzy-matching baseline on the same records.",
  },
  {
    metric: "Review workload",
    text: "The share of records routed to a person, and the median time a reviewer takes.",
  },
];

export const SOLUTIONS: Solution[] = [
  {
    slug: "procurement-and-supply-chain",
    name: "Procurement and supply chain",
    headline: "Know which suppliers share a parent, and what public records say about them.",
    problem:
      "Supplier master data is spread across systems with different spellings. Buyers cannot tell whether two suppliers are the same company, or whether a record at a plant concerns a supplier they use.",
    approach: [
      "Resolve each supplier to a canonical company with a stored score and every candidate considered.",
      "Map ownership so a record at a subsidiary reaches the supplier you buy from, with a lower weight than a direct record.",
      "Show concentration: how many suppliers, and how much spend, sit under one parent.",
    ],
    workflow: [
      "Upload the supplier list and map the columns.",
      "Accept confident matches in bulk and review the rest.",
      "Read each supplier profile with its events and score components.",
      "Receive alerts and export reports for category managers.",
    ],
    measures: MEASURES,
    faq: [
      {
        q: "Can we keep our supplier codes?",
        a: "Yes. Extra columns are kept and returned in exports beside the canonical identifiers.",
      },
      {
        q: "What happens to a row that cannot be matched?",
        a: "It stays unresolved. The product never attaches a record to a company without a stored route and score.",
      },
      {
        q: "How is a subsidiary record weighted?",
        a: "Each relationship type has a weight in the versioned risk configuration. The weights are visible on the score breakdown.",
      },
    ],
  },
  {
    slug: "third-party-risk",
    name: "Third-party risk",
    headline: "Monitor vendors and counterparties against public records, continuously.",
    problem:
      "Periodic reviews miss events between assessments, and manual searches depend on knowing every name a vendor uses.",
    approach: [
      "Resolve vendors once and monitor the canonical company and its family.",
      "Draft one alert per supplier and event, with the source and record date.",
      "Keep an audit trail of who reviewed, accepted, or dismissed each alert and why.",
    ],
    workflow: [
      "Upload vendors or add them one at a time through the API.",
      "Set rules by event type, minimum severity, and vendor tier.",
      "Work the alert queue: acknowledge, assign, comment, or dismiss with a reason.",
      "Export a portfolio report for the committee.",
    ],
    measures: MEASURES,
    faq: [
      {
        q: "Is the output a due diligence decision?",
        a: "No. Signals are leads for human review. Decisions stay with your team.",
      },
      {
        q: "Can alerts go to our own systems?",
        a: "Yes. Alerts can be delivered in the application, by email, and by webhook to an https endpoint.",
      },
      {
        q: "Who can dismiss an alert?",
        a: "Roles with the alert action permission. A reason is required and recorded.",
      },
    ],
  },
  {
    slug: "insurance-and-lending",
    name: "Insurance and lending",
    headline: "Add public-record signals to underwriting and credit review.",
    problem:
      "Underwriters and credit analysts see one legal entity at a time. Records are filed against operating names and locations, and are easy to miss.",
    approach: [
      "Resolve a counterparty to a canonical company and its family.",
      "List regulator records and news events with source links and dates.",
      "Keep evidence with the case through PDF reports and exports.",
    ],
    workflow: [
      "Add a counterparty with name, state, and any identifiers.",
      "Check the resolution evidence and accept or correct it.",
      "Read the event timeline and the score components.",
      "Attach the report to the file.",
    ],
    measures: MEASURES,
    faq: [
      {
        q: "Does the product score creditworthiness?",
        a: "No. The score summarizes public event records for review. It is not a credit score.",
      },
      {
        q: "Can we correct a wrong link?",
        a: "Yes. Submit a correction request. It is stored and routed to the platform review queue.",
      },
      {
        q: "Is customer data used to train models?",
        a: "Only when a tenant opts in, and then without any tenant identifier.",
      },
    ],
  },
  {
    slug: "esg-and-investment-research",
    name: "ESG and investment research",
    headline: "Trace records from facilities to listed parents.",
    problem:
      "Facility-level records rarely name the listed company. Analysts rebuild the link by hand for each issuer.",
    approach: [
      "Use identifiers (SEC CIK, LEI) where they exist and scored matching where they do not.",
      "Follow ownership edges to the ultimate parent with the source and as-of date for each edge.",
      "Distinguish allegations, citations, and recalls from findings of fault.",
    ],
    workflow: [
      "Upload an issuer or supplier list.",
      "Open the family tree and the facilities under each parent.",
      "Review the event timeline by record type.",
      "Export the resolved list and the evidence links.",
    ],
    measures: MEASURES,
    faq: [
      {
        q: "How complete is the ownership graph?",
        a: "It is built from GLEIF, SEC Exhibit 21 filings, and Wikidata. Coverage is stronger for United States listed companies. The methodology page states the limits.",
      },
      {
        q: "Are the records audited?",
        a: "No. They are public records as published by each source, with the retrieval date.",
      },
      {
        q: "Can we cite the data?",
        a: "Each event links to the source record. Cite the source, not the product.",
      },
    ],
  },
];

export const solutionBySlug = (s: string): Solution | undefined =>
  SOLUTIONS.find((x) => x.slug === s);
