import type { Metadata } from "next";
import { Suspense } from "react";
import { ResearchWorkspace } from "@/components/research-workspace";

export const metadata: Metadata = { title: "Company research" };

export default function ResearchPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-[1440px] px-4 py-8 text-sm text-ink-secondary sm:px-6 lg:px-8">
          Loading research workspace…
        </div>
      }
    >
      <ResearchWorkspace />
    </Suspense>
  );
}
