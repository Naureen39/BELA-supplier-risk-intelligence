import { afterEach, describe, expect, it, vi } from "vitest";
import { DemoAccess, demoModeOn } from "@/components/marketing/demo-access";

afterEach(() => vi.unstubAllEnvs());

describe("demo access panel", () => {
  it("is off unless the build turns it on", () => {
    expect(demoModeOn()).toBe(false);
    expect(DemoAccess()).toBeNull();
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");
    expect(DemoAccess()).toBeNull();
  });

  it("shows when demo mode is on", () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "true");
    expect(demoModeOn()).toBe(true);
    expect(DemoAccess()).not.toBeNull();
  });
});
