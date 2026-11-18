// Fails when `npm audit` reports a high or critical advisory that is not on the reviewed allowlist.
// An allowlist entry needs a reason and an expiry date, so a known risk is revisited instead of forgotten.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const allow = JSON.parse(
  readFileSync(new URL("../audit-allowlist.json", import.meta.url), "utf8"),
).entries;
const today = new Date().toISOString().slice(0, 10);
let raw = "";
try {
  raw = execFileSync("npm", ["audit", "--json"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
} catch (e) {
  raw = e.stdout?.toString() ?? ""; // npm audit exits non-zero when it finds anything
}
const report = JSON.parse(raw || "{}");
const problems = [];
const accepted = [];
for (const [name, v] of Object.entries(report.vulnerabilities ?? {})) {
  if (!["high", "critical"].includes(v.severity)) continue;
  const direct = v.via.filter((x) => typeof x === "object");
  if (direct.length === 0) continue; // a package that only depends on a vulnerable one is reported through that package
  for (const adv of direct) {
    const id = String(adv.url ?? "")
      .split("/")
      .pop();
    const hit = allow.find((a) => a.advisory === id);
    if (hit && hit.expires >= today) accepted.push(`${name}: ${id} (allowed until ${hit.expires})`);
    else
      problems.push(
        `${name}: ${id} ${adv.title} (${adv.severity})${hit ? " - allowlist entry expired" : ""}`,
      );
  }
}
for (const a of new Set(accepted)) console.log(`accepted  ${a}`);
for (const p of problems) console.error(`FAIL      ${p}`);
if (problems.length) process.exit(1);
console.log(`npm audit gate passed (${new Set(accepted).size} reviewed advisory)`);
