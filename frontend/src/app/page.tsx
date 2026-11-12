import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BellRing,
  Building2,
  ChevronRight,
  FileText,
  Network,
  Plus,
  Sparkles,
} from "lucide-react";
import { MarketChart } from "@/components/market-chart";
import { ApiStatus } from "@/components/api-status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const announcements = [
  {
    ticker: "DEMO-01",
    company: "Example Industries",
    category: "Results",
    title: "Quarterly results filed · Q2 FY27",
    detail: "Revenue grew 8.4% year-on-year; operating margin widened 40 bps.",
    time: "Today · 08:42",
    priority: "High",
  },
  {
    ticker: "DEMO-02",
    company: "Northstar Components",
    category: "Management change",
    title: "Incoming finance leader announced",
    detail: "A background profile and possible network overlap are ready to review.",
    time: "Today · 07:16",
    priority: "Watch",
  },
  {
    ticker: "DEMO-03",
    company: "Riverstone Materials",
    category: "Capex",
    title: "Capacity expansion approved",
    detail: "Illustrative event card with a contextual network lead.",
    time: "Yesterday · 18:25",
    priority: "Watch",
  },
];

const metrics = [
  { label: "Companies tracked", value: "18", note: "Across 7 sectors", icon: Building2 },
  { label: "Priority items", value: "03", note: "In the selected window", icon: BellRing },
  { label: "Network leads", value: "06", note: "Relevant experience found", icon: Network },
];

function Change({ value, positive = true }: { value: string; positive?: boolean }) {
  const Icon = positive ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${positive ? "text-positive" : "text-negative"}`}>
      <Icon aria-hidden="true" size={14} />
      {value}
    </span>
  );
}

function SectionHeading({
  eyebrow,
  title,
  action,
}: {
  eyebrow?: string;
  title: string;
  action?: string;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        {eyebrow ? <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted">{eyebrow}</p> : null}
        <h2 className="text-[16px] font-semibold tracking-[-0.02em] text-ink">{title}</h2>
      </div>
      {action ? (
        <a className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:text-brand-strong" href="/push">
          {action}<ArrowRight aria-hidden="true" size={14} />
        </a>
      ) : null}
    </div>
  );
}

export default function CommandCentrePage() {
  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 pb-10 pt-5 sm:px-6 sm:pt-8 lg:px-8">
      <div className="mb-6 flex flex-col justify-between gap-4 border-b border-line pb-5 sm:flex-row sm:items-end">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-ink-secondary">Wednesday, 11 November 2026</p>
            <Badge variant="info">Illustrative interface fixture · Not live data</Badge>
          </div>
          <h1 className="text-[26px] font-semibold tracking-[-0.04em] text-ink sm:text-[30px]">Command centre</h1>
          <p className="mt-1 text-sm text-ink-secondary">A focused view of what changed across your portfolio.</p>
        </div>
        <div className="flex items-center gap-2">
          <ApiStatus />
          <Button variant="outline" size="sm" asChild>
            <a href="/settings"><Plus aria-hidden="true" size={15} /> Configure portfolio</a>
          </Button>
        </div>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {metrics.map(({ label, value, note, icon: Icon }) => (
          <section className="rounded-lg border border-line bg-surface p-4 sm:p-5" key={label}>
            <div className="flex items-start justify-between">
              <p className="text-xs font-medium text-ink-secondary">{label}</p>
              <Icon aria-hidden="true" className="text-ink-muted" size={17} strokeWidth={1.8} />
            </div>
            <div className="mt-3 flex items-baseline justify-between gap-2">
              <p className="tabular text-[26px] font-semibold tracking-[-0.04em] text-ink">{value}</p>
              <p className="text-xs text-ink-muted">{note}</p>
            </div>
          </section>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(310px,0.8fr)]">
        <div className="space-y-5">
          <section className="overflow-hidden rounded-lg border border-line bg-surface">
            <div className="flex flex-col justify-between gap-3 border-b border-line px-4 py-4 sm:flex-row sm:items-center sm:px-5">
              <div>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted">Portfolio · EOD overview</p>
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <h2 className="tabular text-[23px] font-semibold tracking-[-0.04em]">₹ 12.84 Cr</h2>
                  <Change value="+1.26% today" />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-xs font-medium text-ink-secondary">Last market close</p>
                  <p className="tabular mt-0.5 text-xs text-ink-muted">10 Nov 2026 · EOD</p>
                </div>
                <Badge variant="neutral">Sample values</Badge>
              </div>
            </div>
            <div className="px-2 pb-2 pt-4 sm:px-4">
              <MarketChart />
            </div>
          </section>

          <section className="rounded-lg border border-line bg-surface p-4 sm:p-5">
            <SectionHeading eyebrow="Push intelligence" title="Priority announcements" action="Open digest" />
            <div className="divide-y divide-line">
              {announcements.map((item) => (
                <article className="py-4 first:pt-1 last:pb-1" key={item.ticker}>
                  <div className="flex items-start gap-3">
                    <span className={`mt-1 h-8 w-[3px] shrink-0 rounded-full ${item.priority === "High" ? "bg-brand" : "bg-caution"}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="tabular text-[11px] font-semibold tracking-wide text-brand">{item.ticker}</span>
                        <span className="text-xs text-ink-muted">{item.company}</span>
                        <Badge variant={item.priority === "High" ? "brand" : "caution"}>{item.priority}</Badge>
                      </div>
                      <h3 className="mt-2 text-sm font-semibold text-ink">{item.title}</h3>
                      <p className="mt-1 text-[13px] leading-5 text-ink-secondary">{item.detail}</p>
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
                        <Badge variant="neutral">{item.category}</Badge>
                        <span>{item.time}</span>
                        <span aria-hidden="true">·</span>
                        <span>Illustrative</span>
                      </div>
                    </div>
                    <a aria-label={`View ${item.company} announcement`} className="mt-1 rounded-md p-2 text-ink-muted hover:bg-surface-muted hover:text-brand" href="/push">
                      <ChevronRight aria-hidden="true" size={17} />
                    </a>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>

        <aside className="space-y-5">
          <section className="rounded-lg border border-line bg-surface p-4 sm:p-5">
            <SectionHeading eyebrow="Market context" title="At a glance" />
            <div className="divide-y divide-line">
              <div className="flex items-center justify-between py-3 first:pt-0">
                <div><p className="text-xs font-medium text-ink">NIFTY 50</p><p className="mt-1 text-[11px] text-ink-muted">EOD · 10 Nov</p></div>
                <div className="text-right"><p className="tabular text-sm font-semibold">24,186.20</p><Change value="+0.42%" /></div>
              </div>
              <div className="flex items-center justify-between py-3">
                <div><p className="text-xs font-medium text-ink">SENSEX</p><p className="mt-1 text-[11px] text-ink-muted">EOD · 10 Nov</p></div>
                <div className="text-right"><p className="tabular text-sm font-semibold">79,488.40</p><Change value="-0.18%" positive={false} /></div>
              </div>
            </div>
            <p className="mt-2 border-t border-line pt-3 text-[11px] leading-4 text-ink-muted">Illustrative values only. Market indices are not yet connected.</p>
          </section>

          <section className="rounded-lg border border-line bg-surface p-4 sm:p-5">
            <SectionHeading eyebrow="Network opportunities" title="A useful next conversation" />
            <div className="rounded-md bg-brand-tint p-3.5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-ink">Example Components</p>
                  <p className="mt-1 text-xs leading-5 text-ink-secondary">A sample portfolio company has a relevant former-operator connection.</p>
                </div>
                <Network aria-hidden="true" className="shrink-0 text-brand" size={18} />
              </div>
              <div className="mt-3 border-t border-brand/10 pt-3">
                <p className="text-xs font-semibold text-ink">Maya R. <span className="ml-1 font-normal text-ink-secondary">· Synthetic profile</span></p>
                <p className="mt-1 text-[11px] leading-4 text-ink-secondary">Former operations lead · Example Components · 2021–24</p>
                <a className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand hover:text-brand-strong" href="/network">
                  Review connection <ArrowRight aria-hidden="true" size={13} />
                </a>
              </div>
            </div>
            <p className="mt-3 text-[11px] text-ink-muted">A relationship lead, not an endorsement or a claim of availability.</p>
          </section>

          <section className="rounded-lg border border-line bg-surface p-4 sm:p-5">
            <SectionHeading eyebrow="Latest intelligence" title="Continue your work" />
            <a className="group flex items-start gap-3 rounded-md p-2 hover:bg-surface-muted" href="/research">
              <span className="rounded-md bg-surface-muted p-2 text-brand"><FileText aria-hidden="true" size={16} /></span>
              <span className="min-w-0 flex-1"><span className="block text-xs font-semibold text-ink">Research a company</span><span className="mt-1 block text-[11px] leading-4 text-ink-muted">Start with any supported NSE ticker</span></span>
              <ArrowRight aria-hidden="true" className="mt-1 text-ink-muted transition-transform group-hover:translate-x-0.5" size={14} />
            </a>
            <a className="group mt-1 flex items-start gap-3 rounded-md p-2 hover:bg-surface-muted" href="/copilot">
              <span className="rounded-md bg-surface-muted p-2 text-brand"><Sparkles aria-hidden="true" size={16} /></span>
              <span className="min-w-0 flex-1"><span className="block text-xs font-semibold text-ink">Ask a source-backed question</span><span className="mt-1 block text-[11px] leading-4 text-ink-muted">Research workspace foundation</span></span>
              <ArrowRight aria-hidden="true" className="mt-1 text-ink-muted transition-transform group-hover:translate-x-0.5" size={14} />
            </a>
          </section>
        </aside>
      </div>
      <p className="mt-6 text-center text-[11px] text-ink-muted">Interface foundation · Sample content is illustrative and not investment research.</p>
    </div>
  );
}
