import type { Metadata } from "next";
import { BellRing, Database, LockKeyhole, SlidersHorizontal } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export const metadata: Metadata = { title: "Settings" };

const groups = [
  {
    title: "Portfolio",
    description: "Configure the companies and supported exchange symbols followed by this workspace.",
    icon: SlidersHorizontal,
  },
  {
    title: "Alert thresholds",
    description: "Choose announcement categories, daily price move thresholds, and volume lookback settings.",
    icon: BellRing,
  },
  {
    title: "Data sources",
    description: "Review source availability, last successful refresh, and stale or delayed data.",
    icon: Database,
  },
  {
    title: "Privacy",
    description: "Review network data provenance, workspace access, retention, and deletion controls.",
    icon: LockKeyhole,
  },
];

export default function SettingsPage() {
  return (
    <div className="mx-auto w-full max-w-[1080px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <div className="mb-6 border-b border-line pb-5">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted">Workspace controls</p>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[26px] font-semibold tracking-[-0.04em] text-ink">Settings</h1>
          <Badge variant="caution">Not persisted</Badge>
        </div>
        <p className="mt-1 text-sm text-ink-secondary">Configure portfolio coverage, signal thresholds, and privacy boundaries.</p>
      </div>
      <div className="space-y-3">
        {groups.map(({ title, description, icon: Icon }) => (
          <section className="flex items-start gap-4 rounded-lg border border-line bg-surface p-4 sm:p-5" key={title}>
            <span className="rounded-md bg-surface-muted p-2 text-ink-secondary"><Icon aria-hidden="true" size={17} /></span>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-ink">{title}</h2>
              <p className="mt-1 text-xs leading-5 text-ink-secondary">{description}</p>
              <p className="mt-2 text-[11px] text-ink-muted">No settings are saved during the foundation phase.</p>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
