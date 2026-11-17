import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthShell } from "@/components/marketing/auth-shell";
import { ResetForm } from "@/components/marketing/password-forms";

export const metadata: Metadata = { title: "Set a new password", robots: { index: false } };

export default function Page() {
  return (
    <AuthShell
      title="Set a new password"
      subtitle="Choose a password that you do not use anywhere else."
    >
      <Suspense>
        <ResetForm />
      </Suspense>
    </AuthShell>
  );
}
