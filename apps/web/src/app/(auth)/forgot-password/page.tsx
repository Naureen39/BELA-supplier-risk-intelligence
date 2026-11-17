import type { Metadata } from "next";
import { AuthShell } from "@/components/marketing/auth-shell";
import { ForgotForm } from "@/components/marketing/password-forms";

export const metadata: Metadata = { title: "Forgot password", robots: { index: false } };

export default function Page() {
  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter your email and we will send a reset link if an account exists."
    >
      <ForgotForm />
    </AuthShell>
  );
}
