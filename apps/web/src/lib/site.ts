export const SITE = {
  name: "Provenance Risk",
  tagline: "Supplier and counterparty risk intelligence",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://localhost:3000",
  email: "contact@provenance-risk.example",
  disclaimer: "Risk signals are leads for human review and not statements of fault.",
} as const;

export interface NavItem {
  title: string;
  href: string;
  description: string;
  icon: IconName;
}

export type IconName =
  | "search"
  | "network"
  | "alert"
  | "gauge"
  | "radar"
  | "code"
  | "briefcase"
  | "shield"
  | "landmark"
  | "leaf"
  | "factory"
  | "car"
  | "utensils"
  | "package"
  | "flask"
  | "truck"
  | "upload"
  | "layers"
  | "file"
  | "users";

export const PLATFORM_NAV: NavItem[] = [
  {
    title: "Entity resolution",
    href: "/platform#resolution",
    icon: "search",
    description: "Match supplier names to canonical companies with a reviewable score.",
  },
  {
    title: "Corporate family",
    href: "/platform#family",
    icon: "network",
    description: "Follow ownership from a facility to its parent.",
  },
  {
    title: "Events",
    href: "/platform#events",
    icon: "alert",
    description: "Regulator records and news events linked to the right company.",
  },
  {
    title: "Risk scoring",
    href: "/platform#risk",
    icon: "gauge",
    description: "A transparent score with every component visible.",
  },
  {
    title: "Monitoring",
    href: "/platform#monitoring",
    icon: "radar",
    description: "Alerts when a supplier or its family appears in new records.",
  },
  {
    title: "API",
    href: "/developers",
    icon: "code",
    description: "Upload suppliers and read risk from your own systems.",
  },
];

export const SOLUTIONS_NAV: NavItem[] = [
  {
    title: "Procurement and supply chain",
    href: "/solutions/procurement-and-supply-chain",
    icon: "briefcase",
    description: "Know which suppliers sit under the same parent.",
  },
  {
    title: "Third-party risk",
    href: "/solutions/third-party-risk",
    icon: "shield",
    description: "Monitor vendors and counterparties continuously.",
  },
  {
    title: "Insurance and lending",
    href: "/solutions/insurance-and-lending",
    icon: "landmark",
    description: "Add public-record signals to underwriting and credit review.",
  },
  {
    title: "ESG and investment research",
    href: "/solutions/esg-and-investment-research",
    icon: "leaf",
    description: "Trace records from facilities to listed parents.",
  },
];

export const INDUSTRY_NAV: NavItem[] = [
  {
    title: "Manufacturing",
    href: "/industries/manufacturing",
    icon: "factory",
    description: "Plant-level safety and environmental records.",
  },
  {
    title: "Automotive",
    href: "/industries/automotive",
    icon: "car",
    description: "Vehicle and equipment recall exposure.",
  },
  {
    title: "Food and beverage",
    href: "/industries/food-and-beverage",
    icon: "utensils",
    description: "Food safety enforcement and recalls.",
  },
  {
    title: "Consumer products",
    href: "/industries/consumer-products",
    icon: "package",
    description: "Product safety recalls across brands.",
  },
  {
    title: "Healthcare and life sciences",
    href: "/industries/healthcare-and-life-sciences",
    icon: "flask",
    description: "Drug and device enforcement records.",
  },
  {
    title: "Logistics",
    href: "/industries/logistics",
    icon: "truck",
    description: "Carrier and warehouse safety signals.",
  },
];

export const RESOURCES_NAV = [
  { title: "Insights", href: "/resources" },
  { title: "Methodology", href: "/methodology" },
  { title: "Developers", href: "/developers" },
  { title: "Security", href: "/security" },
];

export const COMPANY_NAV = [
  { title: "About", href: "/company" },
  { title: "Contact", href: "/contact" },
  { title: "Privacy", href: "/legal/privacy" },
  { title: "Terms", href: "/legal/terms" },
  { title: "Cookies", href: "/legal/cookies" },
];

export const PRICING = {
  label: "Illustrative pricing for the demo environment",
  plans: [
    {
      code: "starter",
      name: "Starter",
      price: "499",
      unit: "per month",
      limit: 250,
      overage: 40,
      blurb: "For a team that wants one monitored supplier list.",
      features: [
        "Up to 250 monitored suppliers",
        "CSV upload and review queue",
        "Regulator and news events",
        "Email alerts",
        "Standard support",
      ],
    },
    {
      code: "professional",
      name: "Professional",
      price: "1,999",
      unit: "per month",
      limit: 2500,
      overage: 120,
      blurb: "For procurement and risk teams with several lists.",
      features: [
        "Up to 2,500 monitored suppliers",
        "Everything in Starter",
        "Corporate family roll-up and alerts",
        "Webhooks and API keys",
        "PDF supplier and portfolio reports",
      ],
    },
    {
      code: "enterprise",
      name: "Enterprise",
      price: "8,000 to 25,000",
      unit: "per month",
      limit: 10000,
      overage: 300,
      blurb: "For large portfolios and shared programs.",
      features: [
        "Portfolio sized to your supply base",
        "Everything in Professional",
        "Tenant roles and mandatory multi-factor sign-in",
        "Audit log access",
        "Named support contact",
      ],
    },
  ],
  annualNote: "Annual billing is discounted by 10 percent.",
  overageNote: "Monitored suppliers above the plan limit are billed per block of 100.",
} as const;
