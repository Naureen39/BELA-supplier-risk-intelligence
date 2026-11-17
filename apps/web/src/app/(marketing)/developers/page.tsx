import type { Metadata } from "next";
import Link from "next/link";
import { CtaBand, PageHero, Section, SectionHead } from "@/components/marketing/blocks";
import { Tabs } from "@/components/ui/tabs";

export const metadata: Metadata = {
  title: "Developers",
  description: "API overview, authentication, code samples, and rate limits.",
  alternates: { canonical: "/developers" },
};

const CURL = `# Upload a supplier list (CSV)
curl -X POST https://your-host/api/v1/uploads \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Idempotency-Key: upload-2026-11-01" \\
  -F "file=@suppliers.csv"

# Read the risk score for one supplier
curl https://your-host/api/v1/suppliers/$SUPPLIER_ID/risk \\
  -H "Authorization: Bearer $API_KEY"`;

const PY = `import os
import httpx

base = "https://your-host/api/v1"
headers = {"Authorization": f"Bearer {os.environ['API_KEY']}"}

with open("suppliers.csv", "rb") as fh:
    upload = httpx.post(f"{base}/uploads", headers=headers,
                        files={"file": ("suppliers.csv", fh, "text/csv")})
upload.raise_for_status()

risk = httpx.get(f"{base}/suppliers/{os.environ['SUPPLIER_ID']}/risk", headers=headers)
body = risk.json()
print(body.get("level"), body["score"])  # score is null until a supplier has been scored`;

const JS = `const base = "https://your-host/api/v1";
const headers = { Authorization: \`Bearer \${process.env.API_KEY}\` };

const form = new FormData();
form.append("file", new Blob([await readFile("suppliers.csv")], { type: "text/csv" }), "suppliers.csv");
const upload = await fetch(\`\${base}/uploads\`, { method: "POST", headers, body: form });
if (!upload.ok) throw new Error(await upload.text());

const risk = await fetch(\`\${base}/suppliers/\${process.env.SUPPLIER_ID}/risk\`, { headers });
console.log(await risk.json());`;

function Code({ children }: { children: string }) {
  return (
    <pre
      className="bg-ink overflow-x-auto rounded-[12px] p-5 font-mono text-[13px] leading-6 text-slate-100"
      tabIndex={0}
      aria-label="Code sample"
    >
      <code>{children}</code>
    </pre>
  );
}

export default function DevelopersPage() {
  return (
    <>
      <PageHero
        eyebrow="Developers"
        title="Upload suppliers and read risk from your own systems"
        text="A JSON API with the same permissions as the application. Interactive reference is served by the API."
      />
      <Section>
        <div className="grid gap-8 md:grid-cols-3">
          {[
            {
              t: "Authentication",
              p: "Create an API key in the application. Send it as a bearer token. Keys are shown once, stored hashed, and carry scopes. Keys cannot call account or administration endpoints.",
            },
            {
              t: "Errors",
              p: "Errors follow RFC 7807 problem documents with a request identifier. Validation messages never echo submitted values.",
            },
            {
              t: "Rate limits",
              p: "Requests are limited per key and per address. Defaults are 600 requests per minute per key, and a limited response carries a Retry-After header. Limits are configurable.",
            },
          ].map((x) => (
            <div key={x.t}>
              <h2 className="text-h4">{x.t}</h2>
              <p className="mt-2 text-[15px] leading-7 text-slate-700">{x.p}</p>
            </div>
          ))}
        </div>
      </Section>
      <Section tone="white">
        <SectionHead eyebrow="Samples" title="Upload a list and read a score" />
        <Tabs
          label="Code samples"
          items={[
            { id: "curl", label: "curl", content: <Code>{CURL}</Code> },
            { id: "python", label: "Python", content: <Code>{PY}</Code> },
            { id: "js", label: "JavaScript", content: <Code>{JS}</Code> },
          ]}
        />
        <p className="mt-6 text-[15px] text-slate-700">
          Uploads are processed asynchronously. Poll the upload for its status, then read results or
          export them with canonical identifiers. The full reference is at{" "}
          <a href="/api/docs" className="text-brand-600 underline underline-offset-2">
            /api/docs
          </a>
          . Methodology and limits are on the{" "}
          <Link href="/methodology" className="text-brand-600 underline underline-offset-2">
            methodology page
          </Link>
          .
        </p>
      </Section>
      <CtaBand />
    </>
  );
}
