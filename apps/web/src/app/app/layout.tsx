import type { Metadata } from "next";
import { AppShell } from "@/components/app/shell";
import { Providers } from "@/components/app/providers";

export const metadata: Metadata = {
  title: { default: "Application", template: "%s | Provenance Risk" },
  robots: { index: false, follow: false },
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <AppShell>{children}</AppShell>
    </Providers>
  );
}
