import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="container-page section-pad text-center">
      <h1 className="text-h1">Page not found</h1>
      <p className="mx-auto mt-4 max-w-md text-[17px] text-slate-700">
        The page may have moved. Return to the home page or read the latest articles.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <Button asChild>
          <Link href="/">Home</Link>
        </Button>
        <Button asChild variant="secondary">
          <Link href="/resources">Resources</Link>
        </Button>
      </div>
    </div>
  );
}
