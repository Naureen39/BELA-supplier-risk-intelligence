"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiRequestError } from "@/lib/api";

interface Me {
  email: string;
  role: string;
  tenant_id: string | null;
}

export default function AppLanding() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/auth/me").then(setMe, (e) => {
      if (e instanceof ApiRequestError && e.status === 401) router.replace("/login");
    });
  }, [router]);

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/login");
  }

  return (
    <main id="main" className="mx-auto max-w-xl px-6 py-20">
      <h1 className="text-h2">Signed in</h1>
      {me ? (
        <dl className="mt-6 space-y-2 text-[16px]">
          <div>
            <dt className="inline font-medium">Email: </dt>
            <dd className="inline">{me.email}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Role: </dt>
            <dd className="inline">{me.role}</dd>
          </div>
        </dl>
      ) : (
        <Skeleton className="mt-6 h-16 w-full" />
      )}
      <p className="mt-6 text-[15px] leading-7 text-slate-700">
        The application workspace (suppliers, review queue, alerts, and analytics) is built in the
        next phase. This page confirms that sign-in and the session work end to end.
      </p>
      <div className="mt-6 flex gap-3">
        <Button onClick={signOut} variant="secondary">
          Sign out
        </Button>
        <Button asChild variant="ghost">
          <Link href="/">Home</Link>
        </Button>
      </div>
    </main>
  );
}
