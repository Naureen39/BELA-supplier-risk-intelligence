"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";

function Confirm() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"working" | "ok" | "bad">(token ? "working" : "bad");
  useEffect(() => {
    if (!token) return;
    api("/newsletter/confirm", { json: { token } }).then(
      () => setState("ok"),
      () => setState("bad"),
    );
  }, [token]);
  return (
    <div className="container-page section-pad">
      <div className="mx-auto max-w-xl text-center">
        <h1 className="text-h1">
          {state === "ok"
            ? "Subscription confirmed"
            : state === "working"
              ? "Confirming"
              : "This link is not valid"}
        </h1>
        <p role="status" className="mt-4 text-[17px] text-slate-700">
          {state === "ok"
            ? "You will receive occasional articles by email."
            : state === "working"
              ? "One moment."
              : "The link may have expired. Subscribe again from the page footer."}
        </p>
        <Link href="/" className="text-brand-600 mt-6 inline-block underline underline-offset-2">
          Back to the home page
        </Link>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Confirm />
    </Suspense>
  );
}
