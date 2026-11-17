import type { Metadata } from "next";
import { CtaBand, PageHero, Section, SectionHead } from "@/components/marketing/blocks";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Security",
  description:
    "Architecture, data protection, access control, audit, retention, and an honest list of what is not claimed.",
  alternates: { canonical: "/security" },
};

const BLOCKS = [
  {
    t: "Architecture summary",
    p: [
      "A web application served over HTTPS proxies all API calls under one origin.",
      "The API is a stateless service in front of PostgreSQL. A cache and message service (Valkey) holds rate limit counters and live alert delivery.",
      "Background work (ingestion, resolution, and report generation) runs separately from request handling.",
    ],
  },
  {
    t: "Data protection",
    p: [
      "Traffic is encrypted with TLS. Sensitive identifiers such as tax identifiers and account numbers are encrypted in the database.",
      "Passwords are hashed with Argon2id and checked against a strength estimator and common password lists.",
      "Multi-factor secrets are stored encrypted. Recovery codes are stored hashed and each works once.",
      "Uploaded files are validated for size and type. Exported spreadsheets neutralize cells that could run as formulas.",
    ],
  },
  {
    t: "Access control",
    p: [
      "Six roles control what a person can see and do: viewer, analyst, manager, tenant administrator, finance analyst, and platform administrator.",
      "Multi-factor sign-in is mandatory for tenant and platform administrators.",
      "Sessions use short-lived access tokens in cookies that scripts cannot read. Refresh tokens rotate on every use, and reuse revokes the whole session.",
      "API keys are scoped, shown once, stored hashed, and cannot reach account or administration endpoints.",
    ],
  },
  {
    t: "Tenant isolation",
    p: [
      "Row level security in the database restricts every query to the caller's tenant.",
      "Automated tests check that one tenant cannot read or change another tenant's rows through the API or through SQL.",
    ],
  },
  {
    t: "Audit",
    p: [
      "Sign-ins, failures, changes to users and keys, review decisions, and report downloads are recorded.",
      "Each audit entry carries a hash of the previous entry, so a removed or edited entry is detectable. The table accepts inserts only.",
    ],
  },
  {
    t: "Retention and data minimization",
    p: [
      "The platform stores snippets and extracted mentions, not full article text.",
      "Each tenant has a retention setting. A scheduled purge job that enforces it is not running yet (see below).",
    ],
  },
  {
    t: "Responsible use and limitations",
    p: [
      "Risk signals are leads for human review and not statements of fault.",
      "Customer feedback is used to improve models only when the tenant opts in, and then without any tenant identifier.",
      "Coverage of structured regulator data is mostly United States.",
    ],
  },
];

const NOT_CLAIMED = [
  "No security certification or attestation is held or claimed. The design is intended to align with common practice, and this is not an audit result.",
  "No independent penetration test report exists yet.",
  "Automated vulnerability and dependency scans run in the project's pipeline where configured. A full scan of the deployed stack has not been completed at the time of writing.",
  "The scheduled data retention purge job is not running yet.",
  "High availability, disaster recovery, and uptime commitments are not offered in the demo environment.",
  "Webhook payloads are not signed yet.",
];

export default function SecurityPage() {
  return (
    <>
      <PageHero
        eyebrow="Security"
        title="How the platform protects supplier data"
        text="This page describes what is built. It is deliberately specific, and it lists what is not claimed."
      />
      <Section>
        <div className="grid gap-6 md:grid-cols-2">
          {BLOCKS.map((b) => (
            <Card key={b.t} className="p-6">
              <h2 className="text-h4">{b.t}</h2>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-[15px] leading-7 text-slate-700">
                {b.p.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      </Section>
      <Section tone="white">
        <SectionHead eyebrow="Honesty" title="What is not claimed" />
        <ul className="max-w-3xl list-disc space-y-3 pl-6 text-[17px] leading-8 text-slate-800">
          {NOT_CLAIMED.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
        <p className="mt-8 max-w-3xl text-[15px] leading-7 text-slate-700">
          To report a vulnerability, write to the contact address on the company page. Please do not
          include customer data.
        </p>
      </Section>
      <CtaBand />
    </>
  );
}
