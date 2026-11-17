"use client";

import { Button } from "@/components/ui/button";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main id="main" className="mx-auto max-w-lg px-6 py-24 text-center">
      <h1 className="text-h2">Something went wrong</h1>
      <p className="mt-3 text-slate-700">
        The page could not be shown. Try again, and if the problem continues, contact us.
      </p>
      <Button className="mt-6" onClick={reset}>
        Try again
      </Button>
    </main>
  );
}
