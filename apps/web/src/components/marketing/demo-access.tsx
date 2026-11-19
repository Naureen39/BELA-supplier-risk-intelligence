/** Demo sign-in instructions. Rendered only when the build sets NEXT_PUBLIC_DEMO_MODE=true. */

const ACCOUNTS: [string, string][] = [
  ["viewer@demo.example", "Read-only. The role used for the public demo."],
  ["analyst@demo.example", "Uploads, reviews matches, acts on alerts."],
  ["manager@demo.example", "Also rules, analytics, and reports."],
  ["admin@demo.example", "Users, API keys, audit log. Sets up MFA at first sign-in."],
  ["finance@demo.example", "Revenue and billing analytics."],
  ["platform@demo.example", "Tenants and the platform review queue. Sets up MFA at first sign-in."],
];

export function demoModeOn(): boolean {
  return process.env.NEXT_PUBLIC_DEMO_MODE === "true";
}

export function DemoAccess() {
  if (!demoModeOn()) return null;
  const viewerPassword = process.env.NEXT_PUBLIC_DEMO_VIEWER_PASSWORD ?? "";
  return (
    <section
      aria-labelledby="demo-access-title"
      className="border-line mt-8 rounded-xl border bg-slate-50 p-5 text-[14px] leading-6 text-slate-700"
    >
      <h2 id="demo-access-title" className="text-ink text-[15px] font-semibold">
        Demo environment
      </h2>
      <p className="mt-1">
        This is a demonstration with synthetic companies and events. Nothing here is real supplier
        data.
      </p>
      {viewerPassword ? (
        <p className="mt-3">
          Read-only access: sign in as <strong>viewer@demo.example</strong> with the password{" "}
          <code className="font-mono">{viewerPassword}</code>.
        </p>
      ) : (
        <p className="mt-3">
          Each account has its own generated password, printed once when the demo was seeded (
          <code className="font-mono">docker compose logs seed</code>). Reset with{" "}
          <code className="font-mono">make demo-reset</code>.
        </p>
      )}
      <ul className="mt-3 space-y-1">
        {ACCOUNTS.map(([email, what]) => (
          <li key={email}>
            <span className="text-ink font-mono text-[13px]">{email}</span>: {what}
          </li>
        ))}
      </ul>
    </section>
  );
}
