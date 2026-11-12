"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  BookOpen,
  Building2,
  Check,
  ChevronDown,
  ExternalLink,
  FileSearch,
  FileText,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NetworkRecommendationsPanel } from "@/components/network-workspace";
import {
  type CompanySearchItem,
  type FinancialPeriod,
  type FinancialResearchReport,
  type ResearchCitation,
  type ResearchClaim,
  type ResearchDiscovery,
  type ResearchDocument,
  type ResearchSection,
  discoverCompany,
  extractDocumentFinancials,
  fetchFinancialPeriods,
  generateFinancialReport,
  ingestDocument,
  searchCompanies,
} from "@/lib/research-api";

type Basis = "standalone" | "consolidated";
type DrawerCitation = ResearchCitation & { source_excerpt?: string | null };

const sectionNavigation = [
  ["overview", "Overview"],
  ["performance", "Performance"],
  ["balance", "Balance sheet"],
  ["cash-flow", "Cash flow"],
  ["guidance", "Guidance"],
  ["narrative", "Narrative"],
  ["bull-bear", "Bull / bear"],
] as const;

const documentTypeLabels: Record<ResearchDocument["document_type"], string> = {
  annual_report: "Annual report",
  quarterly_result: "Quarterly result",
  earnings_call_transcript: "Earnings-call transcript",
  investor_presentation: "Investor presentation",
};

const metricLabels: Record<string, string> = {
  revenue: "Revenue from operations",
  ebitda: "EBITDA",
  pbt: "Profit before tax",
  pat: "Profit after tax",
  total_debt: "Total debt",
  current_borrowings: "Current borrowings",
  non_current_borrowings: "Non-current borrowings",
  cash_and_equivalents: "Cash and equivalents",
  total_equity: "Total equity",
  total_assets: "Total assets",
  current_assets: "Current assets",
  current_liabilities: "Current liabilities",
  trade_receivables: "Trade receivables",
  inventory: "Inventory",
  trade_payables: "Trade payables",
  cash_from_operations: "Cash from operations",
  capital_expenditure: "Capital expenditure",
  free_cash_flow: "Free cash flow",
  ebitda_margin_pct: "EBITDA margin",
  debt_equity_ratio: "Debt / equity",
  net_debt: "Net debt",
  debt_assets_ratio: "Debt / assets",
  current_ratio: "Current ratio",
  receivable_days: "Receivable days",
  inventory_days: "Inventory days",
  payable_days: "Payable days",
  working_capital_cycle_days: "Working-capital cycle",
  roe_pct: "Return on equity",
  roce_pct: "Return on capital employed",
  cash_conversion_ratio: "Cash conversion",
};

function claims(section?: ResearchSection): ResearchClaim[] {
  if (!section) return [];
  return [...section.facts, ...section.calculations, ...section.interpretations];
}

function metricClaim(section: ResearchSection | undefined, key: string) {
  return claims(section).find((claim) => claim.metric_key === key);
}

function formatValue(value: string | null | undefined, currency?: string | null, unit?: string | null) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  const numeric = Number(value);
  const display = Number.isFinite(numeric)
    ? new Intl.NumberFormat("en-IN", {
        maximumFractionDigits: Math.abs(numeric) < 10 ? 2 : 0,
      }).format(numeric)
    : value;
  return [display, currency, unit].filter(Boolean).join(" ");
}

function sourceLabel(citation: ResearchCitation) {
  const page = citation.page_number ? ` · p. ${citation.page_number}` : "";
  const period = citation.reporting_period ? ` · ${citation.reporting_period}` : "";
  return `${citation.document_name}${period}${page}`;
}

function openSource(citation: ResearchCitation) {
  const url = new URL(citation.source_url);
  if (citation.page_number) url.hash = `page=${citation.page_number}`;
  return url.toString();
}

function statusVariant(status?: string): "positive" | "caution" | "neutral" {
  if (status === "ready" || status === "complete" || status === "extracted" || status === "embedded") {
    return "positive";
  }
  if (status === "partial") return "caution";
  return "neutral";
}

function StatusBadge({ status }: { status?: string }) {
  const label = status ? status.replaceAll("_", " ") : "unavailable";
  return <Badge variant={statusVariant(status)}>{label}</Badge>;
}

function EvidenceButton({
  citation,
  onOpen,
}: {
  citation: ResearchCitation;
  onOpen: (citation: DrawerCitation) => void;
}) {
  return (
    <button
      className="inline-flex min-h-8 max-w-full items-center gap-1.5 rounded px-2 text-left text-[11px] font-medium text-info hover:bg-info-tint"
      onClick={() => onOpen(citation)}
      type="button"
    >
      <BookOpen aria-hidden="true" className="shrink-0" size={13} />
      <span className="truncate">{sourceLabel(citation)}</span>
    </button>
  );
}

function ClaimCard({
  claim,
  onCitation,
}: {
  claim: ResearchClaim;
  onCitation: (citation: DrawerCitation) => void;
}) {
  const typeLabel =
    claim.claim_type === "reported_fact"
      ? "Reported"
      : claim.claim_type === "calculation"
        ? "Calculated"
        : "FINN interpretation";
  return (
    <article className="min-w-0 rounded-md border border-line bg-white p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Badge variant={claim.claim_type === "interpretation" ? "info" : "neutral"}>
          {typeLabel}
        </Badge>
        {claim.period_label ? (
          <span className="text-[11px] text-ink-muted">{claim.period_label}</span>
        ) : null}
      </div>
      <p className="break-words text-[13px] leading-5 text-ink">{claim.text}</p>
      {claim.citations.length ? (
        <div className="mt-3 flex flex-wrap gap-1">
          {claim.citations.map((citation, index) => (
            <EvidenceButton
              citation={citation}
              key={`${citation.document_id}-${citation.page_number}-${index}`}
              onOpen={onCitation}
            />
          ))}
        </div>
      ) : null}
    </article>
  );
}

function EmptySection({
  section,
  message,
}: {
  section?: ResearchSection;
  message: string;
}) {
  return (
    <div className="rounded-md border border-dashed border-line bg-surface-muted/60 p-4">
      <div className="flex items-center gap-2">
        <StatusBadge status={section?.status ?? "unavailable"} />
      </div>
      <p className="mt-3 text-sm text-ink-secondary">{message}</p>
      {section?.limitations.map((limitation) => (
        <p className="mt-2 text-xs leading-5 text-ink-muted" key={limitation}>
          {limitation}
        </p>
      ))}
    </div>
  );
}

function SectionHeader({
  eyebrow,
  title,
  description,
  status,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  status?: string;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
          {eyebrow}
        </p>
        <h2 className="mt-1 text-[18px] font-semibold tracking-[-0.025em] text-ink">{title}</h2>
        {description ? <p className="mt-1 text-xs text-ink-secondary">{description}</p> : null}
      </div>
      {status ? <StatusBadge status={status} /> : null}
    </div>
  );
}

function MetricTile({
  label,
  value,
  detail,
  citations,
  onCitation,
}: {
  label: string;
  value: string;
  detail?: string;
  citations?: ResearchCitation[];
  onCitation: (citation: DrawerCitation) => void;
}) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-white p-4">
      <p className="text-[11px] font-medium text-ink-secondary">{label}</p>
      <p className="mt-2 break-words text-[21px] font-semibold tracking-[-0.04em] text-ink tabular">
        {value}
      </p>
      {detail ? <p className="mt-1 text-[11px] text-ink-muted">{detail}</p> : null}
      {citations?.[0] ? (
        <div className="mt-2">
          <EvidenceButton citation={citations[0]} onOpen={onCitation} />
        </div>
      ) : null}
    </div>
  );
}

function CitationDrawer({
  citation,
  onClose,
}: {
  citation: DrawerCitation | null;
  onClose: () => void;
}) {
  if (!citation) return null;
  return (
    <div className="fixed inset-0 z-50 bg-ink/30" onMouseDown={onClose}>
      <aside
        aria-label="Source document details"
        aria-modal="true"
        className="fixed inset-x-0 bottom-0 max-h-[82vh] overflow-y-auto rounded-t-xl border border-line bg-surface p-5 shadow-xl sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[min(460px,100vw)] sm:rounded-none sm:border-l sm:border-t-0 sm:p-7"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
              Primary-source citation
            </p>
            <h2 className="mt-2 text-lg font-semibold leading-6 text-ink">
              {citation.document_name}
            </h2>
          </div>
          <Button aria-label="Close source details" onClick={onClose} size="icon" variant="ghost">
            <X aria-hidden="true" size={18} />
          </Button>
        </div>
        <dl className="mt-6 grid grid-cols-2 gap-4 border-y border-line py-4 text-xs">
          <div>
            <dt className="text-ink-muted">Document type</dt>
            <dd className="mt-1 font-medium text-ink">{citation.document_type.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Reporting period</dt>
            <dd className="mt-1 font-medium text-ink">{citation.reporting_period ?? "Not specified"}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Page</dt>
            <dd className="mt-1 font-medium text-ink">{citation.page_number ?? "Not specified"}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Data label</dt>
            <dd className="mt-1 font-medium text-ink">{citation.is_synthetic ? "Synthetic" : "Primary source"}</dd>
          </div>
        </dl>
        {citation.quote || citation.source_excerpt ? (
          <blockquote className="mt-5 border-l-2 border-brand pl-4 text-sm leading-6 text-ink-secondary">
            {citation.quote ?? citation.source_excerpt}
          </blockquote>
        ) : (
          <p className="mt-5 text-sm text-ink-secondary">
            A page-level excerpt is not available for this source reference.
          </p>
        )}
        <a
          className="mt-6 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white hover:bg-brand-strong"
          href={openSource(citation)}
          rel="noreferrer"
          target="_blank"
        >
          Open original document <ExternalLink aria-hidden="true" size={15} />
        </a>
        <p className="mt-3 break-all text-[10px] leading-4 text-ink-muted">{citation.source_url}</p>
      </aside>
    </div>
  );
}

function FinancialChart({
  title,
  description,
  periods,
  metricKey,
  color,
  onCitation,
}: {
  title: string;
  description: string;
  periods: FinancialPeriod[];
  metricKey: string;
  color: string;
  onCitation: (citation: DrawerCitation) => void;
}) {
  const chartData = periods.map((period) => ({
    period: period.period_label,
    value: period.metrics[metricKey] ? Number(period.metrics[metricKey].value) : null,
    meta: period,
  }));
  const hasData = chartData.some((item) => item.value !== null && Number.isFinite(item.value));
  const unit = periods.find((period) => period.metrics[metricKey])?.unit_scale;
  const currency = periods.find((period) => period.metrics[metricKey])?.currency;
  return (
    <section className="rounded-lg border border-line bg-white p-4 sm:p-5">
      <div>
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        <p className="mt-1 text-[11px] text-ink-muted">
          {description}
          {unit ? ` · ${currency} ${unit}` : ""}
        </p>
      </div>
      {hasData ? (
        <>
          <div className="mt-5 h-56 min-w-0 sm:h-64">
            <ResponsiveContainer height="100%" minWidth={0} width="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
                <CartesianGrid stroke="#e5eaee" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  axisLine={false}
                  dataKey="period"
                  tick={{ fill: "#788695", fontSize: 10 }}
                  tickLine={false}
                />
                <YAxis
                  axisLine={false}
                  tick={{ fill: "#788695", fontSize: 10 }}
                  tickFormatter={(value: number) => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value)}
                  tickLine={false}
                  width={54}
                />
                <Tooltip
                  contentStyle={{ border: "1px solid #dce3e9", borderRadius: 6, fontSize: 12 }}
                  formatter={(value) => [
                    formatValue(String(value ?? ""), currency, unit),
                    title,
                  ]}
                />
                <Line
                  activeDot={{ r: 5, strokeWidth: 0 }}
                  connectNulls={false}
                  dataKey="value"
                  dot={{ fill: color, r: 3, strokeWidth: 0 }}
                  name={title}
                  stroke={color}
                  strokeWidth={2}
                  type="monotone"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-2 border-t border-line pt-3">
            {chartData.map(({ period, value, meta }) => {
              const metric = meta.metrics[metricKey];
              return (
                <div className="flex items-center justify-between gap-3 text-xs" key={meta.period_id}>
                  <span className="text-ink-secondary">{period}</span>
                  {metric ? (
                    <span className="flex min-w-0 items-center gap-1">
                      <span className="truncate font-medium text-ink tabular">{formatValue(metric.value, metric.currency, metric.unit_scale)}</span>
                      <button
                        aria-label={`Open ${meta.document_name} citation for ${period}`}
                        className="rounded p-1 text-info hover:bg-info-tint"
                        onClick={() =>
                          onCitation({
                            document_id: meta.document_id,
                            document_name: meta.document_name,
                            document_type: meta.period_type === "year" ? "annual_report" : "quarterly_result",
                            reporting_period: meta.period_label,
                            page_number: metric.source_page,
                            source_url: metric.source_url,
                            quote: metric.source_excerpt,
                            chunk_id: null,
                            is_synthetic: false,
                          })
                        }
                        type="button"
                      >
                        <BookOpen aria-hidden="true" size={13} />
                      </button>
                    </span>
                  ) : (
                    <span className="text-ink-muted">Unavailable</span>
                  )}
                  {value === null ? <span className="sr-only">Metric unavailable for this period</span> : null}
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div className="mt-5 flex min-h-40 items-center justify-center rounded-md border border-dashed border-line bg-surface-muted/50 px-4 text-center text-sm text-ink-muted">
          No source-backed {title.toLowerCase()} values are available for this basis.
        </div>
      )}
    </section>
  );
}

function FinancialExtractionForm({
  document,
  discoveredPeriod,
  busy,
  onExtract,
}: {
  document: ResearchDocument;
  discoveredPeriod: string | null;
  busy: boolean;
  onExtract: (
    document: ResearchDocument,
    values: {
      period_label: string;
      period_start: string;
      period_end: string;
      period_type: "year" | "quarter";
      reporting_basis: Basis;
      currency: string;
      unit_scale: string;
    },
  ) => Promise<void>;
}) {
  const [periodLabel, setPeriodLabel] = useState(discoveredPeriod ?? "");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [periodType, setPeriodType] = useState<"year" | "quarter">(
    document.document_type === "quarterly_result" ? "quarter" : "year",
  );
  const [basis, setBasis] = useState<Basis | "">("");
  const [currency, setCurrency] = useState("");
  const [unitScale, setUnitScale] = useState("");
  const eligible =
    document.document_type === "annual_report" || document.document_type === "quarterly_result";
  if (!eligible) return null;
  return (
    <details className="mt-3 rounded-md border border-line bg-surface-muted/40">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-3 text-xs font-medium text-ink">
        <span>Extract financial figures</span>
        <ChevronDown aria-hidden="true" className="text-ink-muted" size={15} />
      </summary>
      <form
        className="grid gap-3 border-t border-line p-3 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!basis) return;
          void onExtract(document, {
            period_label: periodLabel.trim(),
            period_start: periodStart,
            period_end: periodEnd,
            period_type: periodType,
            reporting_basis: basis,
            currency: currency.trim().toUpperCase(),
            unit_scale: unitScale.trim().toLowerCase(),
          });
        }}
      >
        <label className="text-[11px] text-ink-secondary">
          Reporting period
          <input
            className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-xs text-ink"
            onChange={(event) => setPeriodLabel(event.target.value)}
            placeholder="e.g. FY2025-26 or Q4 FY2026"
            required
            value={periodLabel}
          />
        </label>
        <label className="text-[11px] text-ink-secondary">
          Period type
          <select
            className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-xs text-ink"
            onChange={(event) => setPeriodType(event.target.value as "year" | "quarter")}
            value={periodType}
          >
            <option value="year">Annual</option>
            <option value="quarter">Quarterly</option>
          </select>
        </label>
        <label className="text-[11px] text-ink-secondary">
          Period start
          <input
            className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-xs text-ink"
            onChange={(event) => setPeriodStart(event.target.value)}
            required
            type="date"
            value={periodStart}
          />
        </label>
        <label className="text-[11px] text-ink-secondary">
          Period end
          <input
            className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-xs text-ink"
            onChange={(event) => setPeriodEnd(event.target.value)}
            required
            type="date"
            value={periodEnd}
          />
        </label>
        <label className="text-[11px] text-ink-secondary">
          Statement basis
          <select
            className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-xs text-ink"
            onChange={(event) => setBasis(event.target.value as Basis | "")}
            required
            value={basis}
          >
            <option value="">Confirm from document</option>
            <option value="consolidated">Consolidated</option>
            <option value="standalone">Standalone</option>
          </select>
        </label>
        <label className="text-[11px] text-ink-secondary">
          Currency
          <input
            className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-xs uppercase text-ink"
            maxLength={3}
            onChange={(event) => setCurrency(event.target.value)}
            placeholder="INR"
            required
            value={currency}
          />
        </label>
        <label className="text-[11px] text-ink-secondary">
          Reported unit
          <input
            className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-xs text-ink"
            onChange={(event) => setUnitScale(event.target.value)}
            placeholder="crore, lakh, million..."
            required
            value={unitScale}
          />
        </label>
        <div className="flex items-end sm:col-span-2 sm:justify-end">
          <Button disabled={busy} size="sm" type="submit">
            {busy ? <LoaderCircle aria-hidden="true" className="animate-spin" size={14} /> : null}
            Extract confirmed values
          </Button>
        </div>
        <p className="text-[10px] leading-4 text-ink-muted sm:col-span-2">
          Confirm these values against the filing before extracting. Ambiguous or missing rows are withheld by the backend.
        </p>
      </form>
    </details>
  );
}

function DocumentCard({
  document,
  ingestion,
  busy,
  onIngest,
  onExtract,
}: {
  document: ResearchDocument;
  ingestion: { status: string; period_label: string | null } | undefined;
  busy: boolean;
  onIngest: (document: ResearchDocument) => void;
  onExtract: Parameters<typeof FinancialExtractionForm>[0]["onExtract"];
}) {
  const status = ingestion?.status ?? document.ingestion_status;
  const isReady = ["extracted", "embedded"].includes(status);
  return (
    <article className="rounded-md border border-line bg-white p-4">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div className="flex min-w-0 gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-brand-tint text-brand">
            <FileText aria-hidden="true" size={16} />
          </span>
          <div className="min-w-0">
            <h3 className="break-words text-sm font-semibold text-ink">{document.title}</h3>
            <p className="mt-1 text-[11px] text-ink-muted">
              {documentTypeLabels[document.document_type]}
              {document.period_label ?? ingestion?.period_label
                ? ` · ${document.period_label ?? ingestion?.period_label}`
                : ""}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge variant="info">Primary source</Badge>
              <StatusBadge status={status} />
            </div>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <a
            aria-label={`Open original ${document.title}`}
            className="inline-flex min-h-10 items-center gap-1.5 rounded-md border border-line px-3 text-xs font-medium text-ink-secondary hover:bg-surface-muted"
            href={document.source_url}
            rel="noreferrer"
            target="_blank"
          >
            Original <ExternalLink aria-hidden="true" size={13} />
          </a>
          {!isReady ? (
            <Button disabled={busy} onClick={() => onIngest(document)} size="sm" type="button">
              {busy ? <LoaderCircle aria-hidden="true" className="animate-spin" size={14} /> : <FileSearch aria-hidden="true" size={14} />}
              Retrieve
            </Button>
          ) : null}
        </div>
      </div>
      {isReady ? (
        <FinancialExtractionForm
          busy={busy}
          discoveredPeriod={ingestion?.period_label ?? document.period_label}
          document={document}
          onExtract={onExtract}
        />
      ) : null}
    </article>
  );
}

export function ResearchWorkspace() {
  const searchParams = useSearchParams();
  const initialTicker = searchParams.get("ticker") ?? "";
  const [query, setQuery] = useState(initialTicker);
  const [suggestions, setSuggestions] = useState<CompanySearchItem[]>([]);
  const [searchError, setSearchError] = useState("");
  const [ticker, setTicker] = useState(initialTicker.trim().toUpperCase());
  const [company, setCompany] = useState<CompanySearchItem | null>(null);
  const [discovery, setDiscovery] = useState<ResearchDiscovery | null>(null);
  const [report, setReport] = useState<FinancialResearchReport | null>(null);
  const [periods, setPeriods] = useState<FinancialPeriod[]>([]);
  const [basis, setBasis] = useState<Basis>("consolidated");
  const [drawerCitation, setDrawerCitation] = useState<DrawerCitation | null>(null);
  const [ingestions, setIngestions] = useState<
    Record<string, { status: string; period_label: string | null }>
  >({});
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) return;
    let active = true;
    const timer = window.setTimeout(() => {
      void searchCompanies(term)
        .then((response) => {
          if (active) {
            setSuggestions(response.results);
            setSearchError("");
          }
        })
        .catch((cause: unknown) => {
          if (active) {
            setSuggestions([]);
            setSearchError(
              cause instanceof Error ? cause.message : "Company search is unavailable.",
            );
          }
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  const updatePeriods = useCallback(async (symbol: string, selectedBasis: Basis) => {
    const response = await fetchFinancialPeriods(symbol, selectedBasis);
    setPeriods(response.periods);
  }, []);

  const chooseCompany = (item: CompanySearchItem) => {
    setCompany(item);
    setTicker(item.ticker);
    setQuery(item.ticker);
    setShowSuggestions(false);
    setDiscovery(null);
    setReport(null);
    setPeriods([]);
    setIngestions({});
    setError("");
    setNotice("");
  };

  async function resolveTicker(value: string) {
    const symbol = value.trim().toUpperCase().replace(/\.NS$/, "");
    if (!symbol) {
      setError("Enter an NSE ticker or choose a company from search results.");
      return null;
    }
    const exact = suggestions.find((item) => item.ticker === symbol);
    if (exact) {
      setCompany(exact);
    } else if (company?.ticker !== symbol) {
      setCompany(null);
    }
    if (ticker !== symbol) {
      setPeriods([]);
      setDiscovery(null);
      setReport(null);
      setIngestions({});
    }
    setTicker(symbol);
    setQuery(symbol);
    setShowSuggestions(false);
    setError("");
    return symbol;
  }

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const symbol = await resolveTicker(query);
    if (symbol) await runDiscovery(symbol);
  }

  async function runDiscovery(symbol = ticker) {
    if (!symbol) {
      setError("Search for a company before discovering its documents.");
      return;
    }
    setBusyAction("discover");
    setError("");
    setNotice("");
    setPeriods([]);
    setReport(null);
    try {
      const result = await discoverCompany(symbol);
      setTicker(result.ticker);
      setDiscovery(result);
      setReport(null);
      const matched = suggestions.find((item) => item.ticker === result.ticker);
      if (matched) setCompany(matched);
      setNotice(
        result.documents.length
          ? `Found ${result.documents.length} issuer documents. Select a filing to retrieve and process it.`
          : `Document discovery completed with status “${result.status}”; no primary documents were returned.`,
      );
      await updatePeriods(result.ticker, basis);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Document discovery failed.");
    } finally {
      setBusyAction("");
    }
  }

  async function runIngestion(document: ResearchDocument) {
    setBusyAction(document.id);
    setError("");
    setNotice("");
    try {
      const result = await ingestDocument(document.id);
      setIngestions((current) => ({
        ...current,
        [document.id]: { status: result.status, period_label: result.period_label },
      }));
      setNotice(
        `Retrieved ${document.title}: ${result.page_count} pages and ${result.chunk_count} page-aware text chunks.`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Document retrieval failed.");
    } finally {
      setBusyAction("");
    }
  }

  async function runExtraction(
    document: ResearchDocument,
    values: {
      period_label: string;
      period_start: string;
      period_end: string;
      period_type: "year" | "quarter";
      reporting_basis: Basis;
      currency: string;
      unit_scale: string;
    },
  ) {
    setBusyAction(document.id);
    setError("");
    setNotice("");
    try {
      const result = await extractDocumentFinancials(document.id, values);
      setBasis(values.reporting_basis);
      await updatePeriods(ticker, values.reporting_basis);
      setNotice(
        `Extracted ${result.extracted_count} reported values. ${
          result.ambiguous_metric_keys.length
            ? `Withheld ambiguous rows: ${result.ambiguous_metric_keys.join(", ")}.`
            : "No ambiguous rows were reported."
        } Generate a fresh report to include them.`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Financial extraction failed.");
    } finally {
      setBusyAction("");
    }
  }

  async function runReport() {
    const symbol = await resolveTicker(query || ticker);
    if (!symbol) return;
    setBusyAction("report");
    setError("");
    setNotice("");
    try {
      let documentResult = discovery;
      if (!documentResult || documentResult.ticker !== symbol) {
        documentResult = await discoverCompany(symbol);
        setDiscovery(documentResult);
        setTicker(documentResult.ticker);
      }
      const generated = await generateFinancialReport(symbol, basis);
      setReport(generated);
      setTicker(generated.ticker);
      await updatePeriods(generated.ticker, basis);
      setNotice(
        generated.status === "complete"
          ? "Research report generated from available primary-source data."
          : `Report generated with ${generated.status} evidence. Missing metrics and periods remain unavailable.`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Report generation failed.");
    } finally {
      setBusyAction("");
    }
  }

  const annualPeriods = useMemo(() => {
    const annual = periods.filter((period) => period.period_type === "year");
    return (annual.length ? annual : periods.filter((period) => period.period_type === "quarter"))
      .slice()
      .sort((left, right) => left.period_end.localeCompare(right.period_end));
  }, [periods]);

  const groupedSources = useMemo(() => {
    if (!report) return [];
    const sources = new Map<
      string,
      { citation: ResearchCitation; referenceCount: number }
    >();
    for (const citation of report.source_manifest) {
      const current = sources.get(citation.document_id);
      if (!current) {
        sources.set(citation.document_id, { citation, referenceCount: 1 });
      } else {
        current.referenceCount += 1;
        if (!current.citation.page_number && citation.page_number) {
          current.citation = citation;
        }
      }
    }
    return [...sources.values()];
  }, [report]);

  const latestPeriod = [...periods].sort((a, b) => b.period_end.localeCompare(a.period_end))[0];
  const basisOptions: Array<{ value: Basis; label: string }> = [
    { value: "consolidated", label: "Consolidated" },
    { value: "standalone", label: "Standalone" },
  ];

  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4 border-b border-line pb-5">
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
            Pull · Primary-source research
          </p>
          <h1 className="text-[26px] font-semibold tracking-[-0.04em] text-ink sm:text-[30px]">
            Company research
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-5 text-ink-secondary">
            A source-led research workspace for any NSE ticker supported by the research service.
          </p>
        </div>
        {report ? (
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={report.is_synthetic ? "caution" : "info"}>
              {report.is_synthetic ? "Synthetic report" : `${report.source_count} primary sources`}
            </Badge>
            <Badge variant={report.status === "complete" ? "positive" : "caution"}>
              {report.status} evidence
            </Badge>
          </div>
        ) : null}
      </div>

      <section className="rounded-lg border border-line bg-surface p-4 sm:p-5">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div className="relative">
            <label className="mb-2 block text-xs font-semibold text-ink" htmlFor="research-search">
              NSE company or ticker
            </label>
            <form className="flex flex-col gap-2 sm:flex-row" onSubmit={handleSearchSubmit} role="search">
              <div className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-md border border-line bg-white px-3 focus-within:ring-2 focus-within:ring-info">
                <Search aria-hidden="true" className="shrink-0 text-ink-muted" size={16} />
                <input
                  autoComplete="off"
                  className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-muted"
                  id="research-search"
                  onBlur={() => window.setTimeout(() => setShowSuggestions(false), 150)}
                  onChange={(event) => {
                    const value = event.target.value;
                    setQuery(value);
                    setShowSuggestions(true);
                    if (value.trim().length < 2) {
                      setSuggestions([]);
                      setSearchError("");
                    }
                  }}
                  onFocus={() => setShowSuggestions(true)}
                  placeholder="Search any supported NSE ticker or company"
                  value={query}
                />
                {query ? (
                  <button
                    aria-label="Clear company search"
                    className="rounded p-1 text-ink-muted hover:bg-surface-muted"
                    onClick={() => {
                      setQuery("");
                      setTicker("");
                      setCompany(null);
                      setDiscovery(null);
                      setReport(null);
                    }}
                    type="button"
                  >
                    <X aria-hidden="true" size={14} />
                  </button>
                ) : null}
              </div>
              <Button disabled={busyAction === "discover"} type="submit">
                {busyAction === "discover" ? (
                  <LoaderCircle aria-hidden="true" className="animate-spin" size={15} />
                ) : (
                  <FileSearch aria-hidden="true" size={15} />
                )}
                Find primary documents
              </Button>
            </form>
            {showSuggestions && (suggestions.length > 0 || searchError) ? (
              <div className="absolute left-0 right-0 top-full z-20 mt-1 max-h-72 overflow-y-auto rounded-md border border-line bg-white p-1 shadow-lg">
                {suggestions.map((item) => (
                  <button
                    className="flex w-full items-center justify-between gap-3 rounded px-3 py-2.5 text-left hover:bg-surface-muted"
                    key={item.company_id}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => chooseCompany(item)}
                    type="button"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <Building2 aria-hidden="true" className="shrink-0 text-ink-muted" size={15} />
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-semibold text-ink">{item.company_name}</span>
                        <span className="mt-0.5 block text-[10px] text-ink-muted">{item.ticker} · {item.exchange}{item.sector ? ` · ${item.sector}` : ""}</span>
                      </span>
                    </span>
                    <span className="flex shrink-0 gap-1">
                      {item.has_primary_documents ? <Badge variant="positive">Sources</Badge> : null}
                      {item.has_financial_data ? <Badge variant="info">Metrics</Badge> : null}
                    </span>
                  </button>
                ))}
                {searchError ? (
                  <p className="px-3 py-2 text-[11px] text-negative">
                    Search service: {searchError}. You can still submit a ticker directly.
                  </p>
                ) : null}
                {suggestions.length === 0 && !searchError ? (
                  <p className="px-3 py-2 text-[11px] text-ink-muted">No existing match. Submit the NSE ticker to discover it.</p>
                ) : null}
              </div>
            ) : null}
            {searchError && !showSuggestions ? (
              <p className="mt-2 text-[11px] text-caution">Company search is unavailable; direct ticker discovery remains available.</p>
            ) : null}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <label className="text-[10px] font-medium text-ink-muted">
              Statement basis
              <select
                className="mt-1 h-11 w-full rounded-md border border-line bg-white px-3 text-xs font-medium text-ink sm:w-36"
                onChange={(event) => {
                  const nextBasis = event.target.value as Basis;
                  setBasis(nextBasis);
                  setPeriods([]);
                  setReport(null);
                  if (ticker) void updatePeriods(ticker, nextBasis).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not load financial periods."));
                }}
                value={basis}
              >
                {basisOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <Button
                disabled={!ticker || busyAction === "report"}
                onClick={() => void runReport()}
                type="button"
                variant="outline"
              >
                {busyAction === "report" ? (
                  <LoaderCircle aria-hidden="true" className="animate-spin" size={15} />
                ) : report ? (
                  <RefreshCw aria-hidden="true" size={15} />
                ) : (
                  <BookOpen aria-hidden="true" size={15} />
                )}
                {report ? "Regenerate report" : "Generate report"}
              </Button>
            </div>
          </div>
        </div>

        {company || discovery ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-semibold tracking-wide text-brand">{ticker}</span>
                {discovery?.company_name || company?.company_name ? (
                  <span className="truncate text-sm font-semibold text-ink">
                    {discovery?.company_name ?? company?.company_name}
                  </span>
                ) : null}
                {company?.sector ? <Badge>{company.sector}</Badge> : null}
              </div>
              <p className="mt-1 text-[11px] text-ink-muted">
                NSE · {basis} statements · {discovery ? `Sources checked ${new Date(discovery.fetched_at).toLocaleString("en-IN")}` : "Select Find primary documents to retrieve issuer filings"}
              </p>
            </div>
            {report ? (
              <p className="text-[11px] text-ink-muted">
                Generated {new Date(report.generated_at).toLocaleString("en-IN")}
              </p>
            ) : null}
          </div>
        ) : (
          <div className="mt-4 flex items-start gap-2 border-t border-line pt-4 text-[11px] leading-5 text-ink-muted">
            <ShieldCheck aria-hidden="true" className="mt-0.5 shrink-0 text-info" size={14} />
            Only issuer/exchange primary documents support research claims. Search results and ticker discovery are live backend data, not a hard-coded demo list.
          </div>
        )}
        {error ? (
          <div aria-live="polite" className="mt-4 flex items-start justify-between gap-3 rounded-md border border-negative/20 bg-negative-tint px-3 py-2.5 text-xs text-negative" role="alert">
            <span>{error}</span>
            <button aria-label="Dismiss error" className="shrink-0" onClick={() => setError("")} type="button"><X size={14} /></button>
          </div>
        ) : null}
        {notice ? (
          <div aria-live="polite" className="mt-4 flex items-start gap-2 rounded-md border border-info/15 bg-info-tint px-3 py-2.5 text-xs leading-5 text-info">
            <Check aria-hidden="true" className="mt-0.5 shrink-0" size={14} />
            <span>{notice}</span>
          </div>
        ) : null}
      </section>

      {discovery ? (
        <section className="mt-5" id="documents">
          <SectionHeader
            description="Retrieved directly from the issuer's investor-relations website. Select a document to ingest and optionally extract statement data."
            eyebrow="Document retrieval"
            status={discovery.status}
            title={`Primary sources · ${discovery.documents.length}`}
          />
          {discovery.documents.length ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {discovery.documents.map((document) => (
                <DocumentCard
                  busy={busyAction === document.id}
                  document={document}
                  ingestion={ingestions[document.id]}
                  key={document.id}
                  onExtract={runExtraction}
                  onIngest={runIngestion}
                />
              ))}
            </div>
          ) : (
            <EmptySection
              message="No primary documents were returned by issuer-site discovery. Try again later or check that the ticker and issuer website are supported."
            />
          )}
        </section>
      ) : null}

      {report ? (
        <>
          <nav aria-label="Research sections" className="sticky top-14 z-10 -mx-4 mt-6 overflow-x-auto border-y border-line bg-canvas/95 px-4 py-2 backdrop-blur sm:top-[68px] sm:mx-0 sm:rounded-md sm:border sm:px-2">
            <div className="flex min-w-max gap-1">
              {sectionNavigation.map(([id, label]) => (
                <a
                  className="rounded px-3 py-2 text-xs font-medium text-ink-secondary hover:bg-brand-tint hover:text-brand"
                  href={`#${id}`}
                  key={id}
                >
                  {label}
                </a>
              ))}
              <a className="rounded px-3 py-2 text-xs font-medium text-ink-secondary hover:bg-brand-tint hover:text-brand" href="#sources">
                Sources
              </a>
            </div>
          </nav>

          <section className="mt-6 scroll-mt-32" id="overview">
            <SectionHeader
              description="Reported company facts and financial snapshot, with each claim linked to its source page."
              eyebrow="Company overview"
              status={report.business_snapshot.status}
              title={report.company_name}
            />
            <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(300px,0.7fr)]">
              <div className="min-w-0 rounded-lg border border-line bg-surface p-4 sm:p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-ink">Business and segments</h3>
                  <Badge variant="info">Source-backed</Badge>
                </div>
                {report.business_snapshot.facts.length ? (
                  <div className="space-y-3">
                    {report.business_snapshot.facts.map((claim, index) => (
                      <ClaimCard claim={claim} key={`business-${index}`} onCitation={setDrawerCitation} />
                    ))}
                  </div>
                ) : (
                  <EmptySection
                    message="Business segment descriptions are unavailable until relevant company-document passages are indexed. Segment names or revenue mix are not inferred."
                    section={report.business_snapshot}
                  />
                )}
              </div>
              <div className="min-w-0">
                <h3 className="mb-3 text-sm font-semibold text-ink">Financial snapshot</h3>
                {report.financial_snapshot.facts.length || report.financial_snapshot.calculations.length ? (
                  <div className="grid grid-cols-2 gap-2">
                    {["revenue", "ebitda", "pbt", "pat"].map((key) => {
                      const claim = metricClaim(report.financial_snapshot, key);
                      return (
                        <MetricTile
                          citations={claim?.citations}
                          detail={claim?.period_label ?? latestPeriod?.period_label}
                          key={key}
                          label={metricLabels[key]}
                          onCitation={setDrawerCitation}
                          value={claim ? formatValue(claim.value, claim.currency, claim.unit_scale) : "Unavailable"}
                        />
                      );
                    })}
                    {(() => {
                      const margin = metricClaim(report.financial_snapshot, "ebitda_margin_pct");
                      return (
                        <MetricTile
                          citations={margin?.citations}
                          detail={margin?.period_label ?? "EBITDA / revenue from operations"}
                          label="EBITDA margin"
                          onCitation={setDrawerCitation}
                          value={margin?.value ? `${Number(margin.value).toFixed(2)}%` : "Unavailable"}
                        />
                      );
                    })()}
                  </div>
                ) : (
                  <EmptySection
                    message="No comparable, non-synthetic primary-source financial metrics are available for this company and statement basis."
                    section={report.financial_snapshot}
                  />
                )}
                {latestPeriod ? (
                  <p className="mt-2 text-[10px] text-ink-muted">
                    Latest extracted period: {latestPeriod.period_label} · {latestPeriod.currency} {latestPeriod.unit_scale} · {latestPeriod.reporting_basis}
                  </p>
                ) : null}
              </div>
            </div>
          </section>

          <div className="mt-4">
            <NetworkRecommendationsPanel
              ticker={report.ticker}
              title={`Reachable contacts with ${report.company_name} context`}
              workflow="who_to_call"
            />
          </div>

          <section className="mt-8 scroll-mt-32" id="performance">
            <SectionHeader
              description={`Source-reported periods · ${annualPeriods.some((item) => item.period_type === "year") ? "annual" : "quarterly"} · ${basis}`}
              eyebrow="Financial trajectory"
              status={report.financial_trajectory.status}
              title="Performance"
            />
            <div className="grid gap-3 lg:grid-cols-3">
              <FinancialChart color="#173b57" description="Reported revenue" metricKey="revenue" onCitation={setDrawerCitation} periods={annualPeriods} title="Revenue" />
              <FinancialChart color="#356a8a" description="Reported EBITDA" metricKey="ebitda" onCitation={setDrawerCitation} periods={annualPeriods} title="EBITDA" />
              <FinancialChart color="#18794e" description="Reported PAT" metricKey="pat" onCitation={setDrawerCitation} periods={annualPeriods} title="PAT" />
            </div>
            {report.financial_trajectory.calculations.length ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {report.financial_trajectory.calculations.map((claim, index) => (
                  <ClaimCard claim={claim} key={`trajectory-${index}`} onCitation={setDrawerCitation} />
                ))}
              </div>
            ) : null}
            {report.financial_trajectory.limitations.map((limitation) => (
              <p className="mt-3 rounded-md bg-caution-tint px-3 py-2 text-xs leading-5 text-caution" key={limitation}>{limitation}</p>
            ))}
          </section>

          <section className="mt-8 scroll-mt-32" id="balance">
            <SectionHeader
              description="Amounts retain filing currency, unit and annual reporting period; ratios are deterministic calculations."
              eyebrow="Financial position"
              status={report.balance_sheet_analysis.status}
              title="Balance-sheet and working-capital analysis"
            />
            {claims(report.balance_sheet_analysis).length ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {claims(report.balance_sheet_analysis).map((claim, index) => (
                  <ClaimCard claim={claim} key={`balance-${claim.metric_key ?? index}`} onCitation={setDrawerCitation} />
                ))}
              </div>
            ) : (
              <EmptySection message="No annual primary-source balance-sheet figures are available." section={report.balance_sheet_analysis} />
            )}
            {report.balance_sheet_analysis.observations.map((observation, index) =>
              typeof observation.convention === "string" ? (
                <p className="mt-3 text-[11px] text-ink-muted" key={`balance-convention-${index}`}>{observation.convention}</p>
              ) : null,
            )}
          </section>

          <section className="mt-8 scroll-mt-32" id="cash-flow">
            <SectionHeader
              description="Cash from operations, capital expenditure, free cash flow and cash conversion; missing inputs stay unavailable."
              eyebrow="Cash quality"
              status={report.cash_quality_analysis.status}
              title="Cash-flow analysis"
            />
            {claims(report.cash_quality_analysis).length ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {claims(report.cash_quality_analysis).map((claim, index) => (
                  <ClaimCard claim={claim} key={`cash-${claim.metric_key ?? index}`} onCitation={setDrawerCitation} />
                ))}
              </div>
            ) : (
              <EmptySection message="Cash from operations and capital spending are not both available from an eligible annual source." section={report.cash_quality_analysis} />
            )}
          </section>

          <section className="mt-8 scroll-mt-32" id="guidance">
            <SectionHeader
              description="Only explicit numerical guidance is compared with matching actuals. Qualitative commentary is not converted into targets."
              eyebrow="Management guidance"
              status={report.management_guidance.status}
              title="Guidance tracker"
            />
            {report.management_guidance.observations.length ? (
              <div className="space-y-3">
                {report.management_guidance.observations.map((raw, index) => {
                  const row = raw as unknown as {
                    statement_date?: string | null;
                    quarter?: string;
                    management_statement?: string;
                    expected_result?: string | null;
                    actual_result?: string | null;
                    variance?: string | null;
                    assessment?: string;
                    citations?: ResearchCitation[];
                  };
                  return (
                    <article className="rounded-lg border border-line bg-white p-4" key={`guidance-${index}`}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-xs font-semibold text-ink">{row.quarter ?? "Period not specified"}</p>
                        <Badge variant={row.assessment === "met" || row.assessment === "exceeded" ? "positive" : row.assessment === "missed" ? "negative" : "caution"}>
                          {(row.assessment ?? "not_yet_verifiable").replaceAll("_", " ")}
                        </Badge>
                      </div>
                      {row.statement_date ? <p className="mt-1 text-[10px] text-ink-muted">Statement date · {row.statement_date}</p> : null}
                      <p className="mt-3 text-sm leading-5 text-ink">{row.management_statement ?? "No management statement available."}</p>
                      <dl className="mt-3 grid grid-cols-1 gap-2 border-t border-line pt-3 text-xs sm:grid-cols-3">
                        <div><dt className="text-ink-muted">Expected</dt><dd className="mt-1 font-medium text-ink">{row.expected_result ?? "Unavailable"}</dd></div>
                        <div><dt className="text-ink-muted">Actual</dt><dd className="mt-1 font-medium text-ink">{row.actual_result ?? "Unavailable"}</dd></div>
                        <div><dt className="text-ink-muted">Variance / status</dt><dd className="mt-1 font-medium text-ink">{row.variance ?? "Not verifiable"}</dd></div>
                      </dl>
                      {row.citations?.map((citation, citationIndex) => (
                        <EvidenceButton citation={citation} key={`guidance-source-${citationIndex}`} onOpen={setDrawerCitation} />
                      ))}
                    </article>
                  );
                })}
              </div>
            ) : (
              <EmptySection message="No indexed earnings-call statements with explicit, verifiable guidance were found for the requested periods." section={report.management_guidance} />
            )}
          </section>

          <section className="mt-8 scroll-mt-32" id="narrative">
            <SectionHeader
              description="Management statements and actual results are presented as reported; interpretation is kept separate."
              eyebrow="Narrative versus numbers"
              status={report.narrative_vs_numbers.status}
              title="What management said · what was delivered"
            />
            {report.narrative_vs_numbers.observations.length ? (
              <div className="space-y-3">
                {report.narrative_vs_numbers.observations.map((raw, index) => {
                  const row = raw as unknown as {
                    quarter?: string;
                    management_statement?: string;
                    expected_result?: string | null;
                    actual_result?: string | null;
                    assessment?: string;
                    citations?: ResearchCitation[];
                  };
                  return (
                    <article className="rounded-lg border border-line bg-white p-4" key={`narrative-${index}`}>
                      <div className="grid gap-3 md:grid-cols-[100px_minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)]">
                        <div><p className="text-[10px] text-ink-muted">Quarter</p><p className="mt-1 text-xs font-semibold text-ink">{row.quarter ?? "Unavailable"}</p></div>
                        <div><p className="text-[10px] text-ink-muted">Management statement</p><p className="mt-1 text-xs leading-5 text-ink">{row.management_statement ?? "Unavailable"}</p></div>
                        <div><p className="text-[10px] text-ink-muted">Expected result</p><p className="mt-1 text-xs leading-5 text-ink">{row.expected_result ?? "No explicit numeric target"}</p></div>
                        <div><p className="text-[10px] text-ink-muted">Actual · assessment</p><p className="mt-1 text-xs leading-5 text-ink">{row.actual_result ?? "Unavailable"} · {(row.assessment ?? "not_yet_verifiable").replaceAll("_", " ")}</p></div>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {row.citations?.map((citation, citationIndex) => (
                          <EvidenceButton citation={citation} key={`narrative-source-${index}-${citationIndex}`} onOpen={setDrawerCitation} />
                        ))}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <EmptySection message="Narrative comparison is unavailable because indexed primary-source earnings-call commentary was not found." section={report.narrative_vs_numbers} />
            )}
          </section>

          <section className="mt-8 scroll-mt-32" id="bull-bear">
            <SectionHeader
              description="Evidence-backed considerations, not forecasts or buy/sell recommendations."
              eyebrow="Balanced assessment"
              status={report.bull_vs_bear.status}
              title="Bull case and bear case"
            />
            {report.bull_vs_bear.interpretations.length ? (
              <div className="grid gap-3 md:grid-cols-2">
                {(["bull", "bear"] as const).map((side) => {
                  const items = report.bull_vs_bear.interpretations.filter((claim) =>
                    claim.text.toLowerCase().startsWith(`${side} case:`),
                  );
                  return (
                    <div className="rounded-lg border border-line bg-white p-4" key={side}>
                      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
                        {side === "bull" ? <ArrowUpRight aria-hidden="true" className="text-positive" size={16} /> : <ArrowDownRight aria-hidden="true" className="text-negative" size={16} />}
                        {side === "bull" ? "Bull case" : "Bear case"}
                      </h3>
                      {items.length ? (
                        <div className="mt-3 space-y-3">
                          {items.map((claim, index) => <ClaimCard claim={claim} key={`${side}-${index}`} onCitation={setDrawerCitation} />)}
                        </div>
                      ) : (
                        <p className="mt-3 text-xs leading-5 text-ink-muted">No source-supported {side} consideration is available.</p>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptySection message="There is insufficient comparable annual financial evidence to form a balanced bull/bear view." section={report.bull_vs_bear} />
            )}
            <p className="mt-3 text-[10px] text-ink-muted">
              FINN analytical considerations are based on historical evidence only. They are not investment recommendations.
            </p>
          </section>

          <section className="mt-8 scroll-mt-32" id="sources">
            <SectionHeader
              description="Every factual claim links to a primary-source page when available. Original PDFs open in a separate tab."
              eyebrow="Provenance"
              title={`Source documents · ${groupedSources.length}`}
            />
            {groupedSources.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {groupedSources.map(({ citation, referenceCount }) => (
                  <button
                    className="flex min-h-16 items-center justify-between gap-3 rounded-md border border-line bg-white px-4 py-3 text-left hover:bg-surface-muted"
                    key={citation.document_id}
                    onClick={() => setDrawerCitation(citation)}
                    type="button"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-semibold text-ink">{citation.document_name}</span>
                      <span className="mt-1 block text-[10px] text-ink-muted">
                        {citation.document_type.replaceAll("_", " ")}
                        {citation.reporting_period ? ` · ${citation.reporting_period}` : ""}
                        {citation.page_number ? ` · sample p. ${citation.page_number}` : ""}
                        {` · ${referenceCount} page ${referenceCount === 1 ? "reference" : "references"}`}
                      </span>
                    </span>
                    <ExternalLink aria-hidden="true" className="shrink-0 text-ink-muted" size={15} />
                  </button>
                ))}
              </div>
            ) : (
              <EmptySection message="No eligible, non-synthetic primary-source citations are attached to this report." />
            )}
          </section>
        </>
      ) : null}

      {!report && !discovery ? (
        <section className="mt-5 grid gap-3 sm:grid-cols-3">
          {[
            ["01", "Search an NSE issuer", "Search the backend company universe or enter a supported ticker directly."],
            ["02", "Retrieve primary sources", "Discover issuer documents, open original filings and process selected PDFs."],
            ["03", "Generate evidence-led analysis", "Review only extracted financial figures, explicit guidance and page-level citations."],
          ].map(([number, title, description]) => (
            <div className="rounded-lg border border-line bg-surface p-4" key={number}>
              <span className="font-mono text-[11px] text-brand">{number}</span>
              <h2 className="mt-3 text-sm font-semibold text-ink">{title}</h2>
              <p className="mt-1 text-xs leading-5 text-ink-secondary">{description}</p>
            </div>
          ))}
        </section>
      ) : null}

      {report && !periods.length ? (
        <div className="mt-5 rounded-md border border-caution/20 bg-caution-tint p-3 text-xs leading-5 text-caution">
          The report has no extracted financial periods for {basis} statements. Retrieve a primary financial filing, confirm its period, basis, currency and reported unit, then extract its values before regenerating.
        </div>
      ) : null}
      <CitationDrawer citation={drawerCitation} onClose={() => setDrawerCitation(null)} />
    </div>
  );
}
