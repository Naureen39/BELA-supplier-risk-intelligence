import { describe, expect, it } from "vitest";
import { resolveRange } from "@/components/app/range-bar";
import { ago, csvCell, label, pct, toCsv, usd } from "@/lib/app/format";
import { can, NAV, type Me } from "@/lib/app/session";

const me = (permissions: string[]): Me => ({
  id: "1",
  email: "a@b.example",
  role: "viewer",
  tenant_id: "t",
  permissions,
  mfa_enabled: false,
});

describe("formatting", () => {
  it("formats money, percent, and labels", () => {
    expect(usd(1234567)).toBe("$1,234,567");
    expect(usd(null)).toBe("n/a");
    expect(pct(12.345)).toBe("12.3%");
    expect(label("workplace_safety")).toBe("Workplace safety");
  });
  it("describes recent times", () => {
    expect(ago(new Date().toISOString())).toBe("just now");
    expect(ago(new Date(Date.now() - 3 * 3600_000).toISOString())).toBe("3 h ago");
  });
});

describe("CSV export", () => {
  it("neutralizes cells a spreadsheet would run as formulas", () => {
    for (const bad of ["=SUM(A1)", "+1", "-1", "@cmd", "\tTab"])
      expect(csvCell(bad).replace(/"/g, "").startsWith("'")).toBe(true);
  });
  it("quotes commas, quotes, and newlines", () => {
    expect(csvCell('a,"b"')).toBe('"a,""b"""');
    expect(toCsv([{ a: 1, b: "x\ny" }])).toBe('a,b\n1,"x\ny"');
  });
});

describe("date ranges", () => {
  const end = new Date("2026-10-31T00:00:00Z");
  it("resolves presets to inclusive windows ending at the latest data", () => {
    expect(resolveRange({ preset: "30d", granularity: "day", compare: false }, end)).toEqual({
      from: "2026-10-02",
      to: "2026-10-31",
    });
    expect(resolveRange({ preset: "12m", granularity: "month", compare: false }, end).from).toBe(
      "2025-11-01",
    );
    expect(resolveRange({ preset: "all", granularity: "month", compare: false }, end)).toEqual({});
    expect(
      resolveRange(
        {
          preset: "custom",
          from: "2026-01-01",
          to: "2026-02-01",
          granularity: "day",
          compare: true,
        },
        end,
      ),
    ).toEqual({ from: "2026-01-01", to: "2026-02-01" });
  });
});

describe("navigation and permissions", () => {
  it("shows only what a role's permissions allow", () => {
    const viewer = me(["view"]);
    const visible = NAV.filter((n) => can(viewer, n.permission)).map((n) => n.label);
    expect(visible).toEqual(["Overview", "Suppliers", "Alerts", "Events", "Explorer", "Settings"]);
    const finance = me(["view_revenue"]);
    expect(NAV.filter((n) => can(finance, n.permission)).map((n) => n.label)).toEqual(["Revenue"]);
    expect(can(undefined, "view")).toBe(false);
  });
  it("uses permission names that exist in the API's matrix", () => {
    const api = [
      "view",
      "upload_review",
      "alert_action",
      "manage_rules",
      "manage_users",
      "view_audit",
      "view_revenue",
      "platform",
    ];
    for (const n of NAV) expect(api, n.href).toContain(n.permission);
  });
});
