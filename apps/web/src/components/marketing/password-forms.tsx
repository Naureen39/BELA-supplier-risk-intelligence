"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { api, ApiRequestError } from "@/lib/api";

export function ForgotForm() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/password/forgot", { json: { email } });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiRequestError && err.status === 429
          ? "Too many requests. Try again later."
          : "Enter a valid email address.",
      );
    } finally {
      setBusy(false);
    }
  }
  if (done) {
    return (
      <p role="status" className="bg-brand-100 text-ink rounded-[8px] p-4 text-[15px] leading-7">
        If the account exists, a reset email has been sent. The link expires after a short time.
      </p>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <Field id="email" label="Email">
        {(a) => (
          <Input
            {...a}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        )}
      </Field>
      {error && (
        <p role="alert" className="text-danger text-sm">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" className="w-full" disabled={busy}>
        {busy ? "Sending" : "Send reset link"}
      </Button>
      <p className="text-sm">
        <Link href="/login" className="text-brand-600 underline underline-offset-2">
          Back to sign in
        </Link>
      </p>
    </form>
  );
}

export function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!token)
    return (
      <p role="alert" className="text-danger text-[15px]">
        This link is missing its token. Request a new reset email.
      </p>
    );
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) return void setError("The passwords do not match.");
    setBusy(true);
    setError("");
    try {
      await api("/auth/password/reset", { json: { token, password } });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? (err.problem.detail ?? "The link is not valid or the password was rejected.")
          : "The request could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }
  if (done) {
    return (
      <div role="status" className="space-y-4">
        <p className="rounded-[8px] bg-[#e3f4ec] p-4 text-[15px] text-[#176e47]">
          The password has been changed. Sign in again.
        </p>
        <Button asChild size="lg" className="w-full">
          <Link href="/login">Go to sign in</Link>
        </Button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <Field
        id="password"
        label="New password"
        hint="At least 12 characters. A long phrase works well."
      >
        {(a) => (
          <Input
            {...a}
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        )}
      </Field>
      <Field id="confirm" label="Confirm password">
        {(a) => (
          <Input
            {...a}
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        )}
      </Field>
      {error && (
        <p role="alert" className="rounded-[8px] bg-[#fbe4e1] p-3 text-sm text-[#9b2c20]">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" className="w-full" disabled={busy}>
        {busy ? "Saving" : "Set new password"}
      </Button>
    </form>
  );
}
