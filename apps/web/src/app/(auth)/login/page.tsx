import type { Metadata } from "next";
import { AuthShell } from "@/components/marketing/auth-shell";
import { DemoAccess } from "@/components/marketing/demo-access";
import { LoginFlow } from "@/components/marketing/login-flow";

export const metadata: Metadata = {
  title: "Log in",
  robots: { index: false },
  alternates: { canonical: "/login" },
};

export default function LoginPage() {
  return (
    <AuthShell
      title="Log in"
      subtitle="Sign in to review matches, monitor suppliers, and read reports."
    >
      <LoginFlow />
      <DemoAccess />
    </AuthShell>
  );
}
