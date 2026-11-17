"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { api, ApiRequestError } from "@/lib/api";

type Step = "credentials" | "mfa" | "enroll";
interface LoginResponse {
  status: string;
  mfa_token?: string;
}
interface Setup {
  secret: string;
  otpauth_uri: string;
  recovery_codes: string[];
}

function message(e: unknown): string {
  if (e instanceof ApiRequestError) {
    if (e.status === 429) return "Too many attempts. Wait a few minutes and try again.";
    if (e.status === 401 || e.status === 403 || e.status === 423)
      return e.problem.detail ?? "The email, password, or code is not correct.";
    if (e.status === 422) return "Check the fields and try again.";
  }
  return "Sign-in is not available right now. Try again shortly.";
}

export function LoginFlow() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [mfaToken, setMfaToken] = useState("");
  const [setup, setSetup] = useState<Setup | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  const submitCredentials = (e: React.FormEvent) => {
    e.preventDefault();
    return run(async () => {
      const r = await api<LoginResponse>("/auth/login", { json: { email, password } });
      if (r.status === "authenticated") return void router.push("/app");
      setMfaToken(r.mfa_token ?? "");
      if (r.status === "mfa_enrollment_required") {
        setSetup(await api<Setup>("/auth/mfa/setup", { json: { mfa_token: r.mfa_token } }));
        setStep("enroll");
      } else {
        setStep("mfa");
      }
    });
  };

  const submitCode = (e: React.FormEvent) => {
    e.preventDefault();
    return run(async () => {
      await api("/auth/mfa/verify", {
        json: {
          mfa_token: mfaToken,
          ...(useRecovery ? { recovery_code: code.trim() } : { code: code.trim() }),
        },
      });
      router.push("/app");
    });
  };

  if (step === "credentials") {
    return (
      <form onSubmit={submitCredentials} className="space-y-5" noValidate>
        <Field id="email" label="Email">
          {(a) => (
            <Input
              {...a}
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Field id="password" label="Password">
          {(a) => (
            <Input
              {...a}
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        {error && (
          <p role="alert" className="rounded-[8px] bg-[#fbe4e1] p-3 text-sm text-[#9b2c20]">
            {error}
          </p>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? "Signing in" : "Sign in"}
        </Button>
        <p className="text-sm">
          <Link href="/forgot-password" className="text-brand-600 underline underline-offset-2">
            Forgot your password?
          </Link>
        </p>
      </form>
    );
  }

  return (
    <div className="space-y-6">
      {step === "enroll" && setup && (
        <section aria-labelledby="enroll-h" className="space-y-4">
          <h2 id="enroll-h" className="text-h4">
            Set up multi-factor sign-in
          </h2>
          <p className="text-[15px] leading-7 text-slate-700">
            Your role requires multi-factor sign-in. Scan the code with an authenticator app, or
            enter the key by hand.
          </p>
          <div className="border-line inline-block rounded-[12px] border bg-white p-3">
            <QRCodeSVG value={setup.otpauth_uri} size={160} title="Authenticator setup code" />
          </div>
          <p className="text-ink font-mono text-sm break-all">{setup.secret}</p>
          <div>
            <p className="text-ink text-sm font-medium">Recovery codes</p>
            <p className="text-sm text-slate-700">
              Each code works once. They are shown now only. Store them somewhere safe.
            </p>
            <ul className="text-ink mt-2 grid grid-cols-2 gap-1 font-mono text-sm">
              {setup.recovery_codes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        </section>
      )}
      <form onSubmit={submitCode} className="space-y-5" noValidate>
        <Field
          id="code"
          label={useRecovery ? "Recovery code" : "Six-digit code"}
          hint={
            step === "enroll"
              ? "Enter the current code from the app to finish."
              : "Open your authenticator app."
          }
        >
          {(a) => (
            <Input
              {...a}
              inputMode={useRecovery ? "text" : "numeric"}
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          )}
        </Field>
        {error && (
          <p role="alert" className="rounded-[8px] bg-[#fbe4e1] p-3 text-sm text-[#9b2c20]">
            {error}
          </p>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? "Verifying" : "Verify and continue"}
        </Button>
        {step === "mfa" && (
          <button
            type="button"
            className="text-brand-600 text-sm underline underline-offset-2"
            onClick={() => {
              setUseRecovery(!useRecovery);
              setCode("");
            }}
          >
            {useRecovery ? "Use an authenticator code" : "Use a recovery code"}
          </button>
        )}
      </form>
    </div>
  );
}
