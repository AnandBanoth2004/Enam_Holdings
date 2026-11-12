"use client";

import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Bell,
  CalendarClock,
  Check,
  ChevronRight,
  CircleHelp,
  ExternalLink,
  FileText,
  Filter,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NetworkRecommendationsPanel } from "@/components/network-workspace";
import {
  announcementCategories,
  type AlertConfiguration,
  type AlertHistoryItem,
  type Announcement,
  type AnnouncementCategory,
  type DigestWindow,
  type FinancialMetricComparison,
  type Materiality,
  type Priority,
  type ResultsComparison,
  fetchAlertConfiguration,
  fetchAlertHistory,
  fetchAnnouncement,
  fetchDigest,
  fetchMateriality,
  fetchResults,
  saveAlertConfiguration,
  updateAlertStatus,
} from "@/lib/push-api";
import { cn } from "@/lib/utils";

const priorityStyles: Record<Priority, string> = {
  critical: "border-negative/20 bg-negative-tint text-negative",
  high: "border-caution/20 bg-caution-tint text-caution",
  medium: "border-info/20 bg-info-tint text-info",
  low: "border-line bg-surface-muted text-ink-secondary",
};

function formatFiledAt(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function formatNumber(value: string | null) {
  if (value === null || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(
    Number(value),
  );
}

function formatPercent(value: string | null) {
  if (value === null || !Number.isFinite(Number(value))) return null;
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}%`;
}

function sourceIsHttp(url: string) {
  return url.startsWith("https://") || url.startsWith("http://");
}

function dateToIso(value: string, endOfDay = false) {
  return new Date(
    `${value}T${endOfDay ? "23:59:59" : "00:00:00"}+05:30`,
  ).toISOString();
}

function isPriority(value: string): value is Priority {
  return ["critical", "high", "medium", "low"].includes(value);
}

function DemoBadge({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return <Badge variant="caution">DEMO ONLY</Badge>;
}

function SectionHeading({
  step,
  eyebrow,
  title,
  description,
  action,
}: {
  step: string;
  eyebrow: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-line bg-white text-[11px] font-semibold text-ink-muted">
          {step}
        </span>
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
            {eyebrow}
          </p>
          <h2 className="mt-1 text-[16px] font-semibold tracking-[-0.02em] text-ink">
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-xs leading-5 text-ink-secondary">
              {description}
            </p>
          ) : null}
        </div>
      </div>
      {action}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div
      aria-hidden="true"
      className="animate-pulse rounded-lg border border-line bg-surface p-4 sm:p-5"
    >
      <div className="flex justify-between gap-4">
        <div className="h-3 w-24 rounded bg-surface-muted" />
        <div className="h-5 w-16 rounded-full bg-surface-muted" />
      </div>
      <div className="mt-4 h-4 w-4/5 rounded bg-surface-muted" />
      <div className="mt-3 h-3 w-full rounded bg-surface-muted" />
      <div className="mt-2 h-3 w-3/4 rounded bg-surface-muted" />
      <div className="mt-5 h-2 w-full rounded bg-surface-muted" />
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="rounded-lg border border-negative/20 bg-negative-tint/60 p-4"
      role="alert"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 shrink-0 text-negative" size={17} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">Push data unavailable</p>
          <p className="mt-1 text-xs leading-5 text-ink-secondary">{message}</p>
          {onRetry ? (
            <Button
              className="mt-3"
              onClick={onRetry}
              size="sm"
              type="button"
              variant="outline"
            >
              <RefreshCw size={13} />
              Retry
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function MetricTile({
  metric,
  results,
}: {
  metric: FinancialMetricComparison;
  results: ResultsComparison;
}) {
  const qoq = formatPercent(metric.qoq_percent_change);
  const yoy = formatPercent(metric.yoy_percent_change);
  const currentSynthetic =
    metric.current.is_synthetic || metric.qoq.is_synthetic || metric.yoy.is_synthetic;
  return (
    <div className="min-w-0 rounded-md border border-line bg-white p-3 sm:p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
          {metric.metric_key}
        </p>
        <DemoBadge visible={currentSynthetic} />
      </div>
      <p className="mt-2 truncate text-[18px] font-semibold tracking-[-0.03em] text-ink tabular">
        {formatNumber(metric.current.value)}
        <span className="ml-1 text-[10px] font-medium text-ink-muted">
          {results.currency} {results.unit_scale}
        </span>
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-2.5">
        <ComparisonValue
          absoluteChange={metric.qoq_absolute_change}
          label="QoQ"
          note={metric.qoq_change_note ?? metric.qoq.reason}
          unit={`${results.currency} ${results.unit_scale}`}
          value={qoq}
        />
        <ComparisonValue
          absoluteChange={metric.yoy_absolute_change}
          label="YoY"
          note={metric.yoy_change_note ?? metric.yoy.reason}
          unit={`${results.currency} ${results.unit_scale}`}
          value={yoy}
        />
      </div>
      {metric.current.reason ? (
        <p className="mt-2 text-[10px] leading-4 text-ink-muted">
          {metric.current.reason}
        </p>
      ) : null}
      {metric.current.source_url && sourceIsHttp(metric.current.source_url) ? (
        <a
          className="mt-3 inline-flex min-h-8 items-center gap-1 text-[11px] font-medium text-brand hover:underline"
          href={metric.current.source_url}
          rel="noreferrer"
          target="_blank"
        >
          Primary source <ExternalLink size={12} />
        </a>
      ) : null}
    </div>
  );
}

function ComparisonValue({
  label,
  value,
  absoluteChange,
  unit,
  note,
}: {
  label: string;
  value: string | null;
  absoluteChange: string | null;
  unit: string;
  note: string | null;
}) {
  const positive = value?.startsWith("+");
  const negative = value?.startsWith("-");
  const Icon = negative ? ArrowDownRight : ArrowUpRight;
  return (
    <div>
      <p className="text-[10px] text-ink-muted">{label}</p>
      <p
        className={cn(
          "mt-0.5 inline-flex items-center gap-0.5 text-xs font-semibold tabular",
          positive && "text-positive",
          negative && "text-negative",
          !value && "text-ink-muted",
        )}
      >
        {value ? <Icon size={12} /> : null}
        {value ?? "—"}
      </p>
      <p className="mt-1 line-clamp-2 text-[9px] leading-4 text-ink-muted" title={note ?? undefined}>
        {absoluteChange !== null
          ? `Δ ${formatNumber(absoluteChange)} ${unit}`
          : note ?? "No comparison value available"}
      </p>
    </div>
  );
}

function AnnouncementCard({
  announcement,
  selected,
  relatedAlert,
  onSelect,
}: {
  announcement: Announcement;
  selected: boolean;
  relatedAlert: boolean;
  onSelect: () => void;
}) {
  const priority = isPriority(announcement.priority)
    ? announcement.priority
    : "low";
  const score = Math.max(0, Math.min(100, announcement.materiality_score ?? 0));
  return (
    <article
      className={cn(
        "rounded-lg border bg-surface p-4 transition-colors sm:p-5",
        selected ? "border-brand/40 ring-1 ring-brand/10" : "border-line",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold text-ink">
            {announcement.ticker || announcement.company_name}
          </span>
          <span className="text-[11px] text-ink-muted">{announcement.company_name}</span>
          <Badge variant="neutral">{announcement.category}</Badge>
          <DemoBadge visible={announcement.is_synthetic} />
        </div>
        <Badge className={priorityStyles[priority]} variant="neutral">
          {priority}
        </Badge>
      </div>
      <h3 className="mt-3 text-[14px] font-semibold leading-5 text-ink">
        {announcement.headline}
      </h3>
      <p className="mt-2 text-xs leading-5 text-ink-secondary">
        {announcement.summary}
      </p>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[10px] text-ink-muted">
          <CalendarClock size={13} />
          <time dateTime={announcement.filed_at}>{formatFiledAt(announcement.filed_at)} IST</time>
        </div>
        <div className="flex items-center gap-2">
          {relatedAlert ? <Badge variant="positive">Alert created</Badge> : null}
          <span className="text-[10px] font-medium text-ink-secondary tabular">
            {announcement.materiality_score ?? "—"}/100
          </span>
        </div>
      </div>
      <div
        aria-label={`Materiality score ${score} out of 100`}
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted"
        role="img"
      >
        <div
          className={cn(
            "h-full rounded-full",
            priority === "critical" || priority === "high"
              ? "bg-caution"
              : priority === "medium"
                ? "bg-info"
                : "bg-ink-muted",
          )}
          style={{ width: `${score}%` }}
        />
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] text-ink-muted">
          Rule-based materiality · source timestamped
        </span>
        <Button onClick={onSelect} size="sm" type="button" variant="outline">
          Review announcement
          <ChevronRight size={14} />
        </Button>
      </div>
    </article>
  );
}

function AnnouncementDetail({
  announcement,
  materiality,
  loading,
  error,
  alertLinked,
  onClose,
}: {
  announcement: Announcement | null;
  materiality: Materiality | null;
  loading: boolean;
  error: string | null;
  alertLinked: boolean;
  onClose: () => void;
}) {
  if (!announcement && !loading && !error) {
    return (
      <div className="rounded-lg border border-dashed border-line bg-surface p-6 text-center">
        <span className="mx-auto flex size-10 items-center justify-center rounded-full bg-brand-tint text-brand">
          <FileText size={17} />
        </span>
        <p className="mt-3 text-sm font-semibold text-ink">Select a filing to inspect</p>
        <p className="mt-1 text-xs leading-5 text-ink-secondary">
          Open an announcement to see its source record, materiality rules, and linked alert.
        </p>
      </div>
    );
  }
  return (
    <section
      aria-labelledby="announcement-detail-title"
      className="rounded-lg border border-line bg-surface p-4 sm:p-5"
      id="announcement-detail"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
            Selected filing
          </p>
          <h2
            className="mt-1 text-[15px] font-semibold leading-5 text-ink"
            id="announcement-detail-title"
          >
            {announcement?.headline ?? "Loading announcement"}
          </h2>
        </div>
        <Button
          aria-label="Close announcement details"
          onClick={onClose}
          size="icon"
          type="button"
          variant="ghost"
        >
          <X size={16} />
        </Button>
      </div>
      {loading ? (
        <div className="mt-5 space-y-3" role="status" aria-label="Loading announcement details">
          <div className="h-3 w-2/3 animate-pulse rounded bg-surface-muted" />
          <div className="h-3 w-full animate-pulse rounded bg-surface-muted" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-surface-muted" />
        </div>
      ) : error ? (
        <p className="mt-4 rounded-md bg-negative-tint p-3 text-xs text-negative" role="alert">
          {error}
        </p>
      ) : announcement ? (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge variant="brand">{announcement.ticker} · {announcement.category}</Badge>
            <DemoBadge visible={announcement.is_synthetic} />
            {alertLinked ? <Badge variant="positive">Linked alert in history</Badge> : null}
          </div>
          <p className="mt-3 text-xs leading-5 text-ink-secondary">
            {announcement.summary}
          </p>
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-y border-line py-3 text-[11px] text-ink-secondary">
            <span>Filed {formatFiledAt(announcement.filed_at)} IST</span>
            <span>
              Source: {String(announcement.source_metadata.source ?? "unknown")}
            </span>
            <span>
              Confidence:{" "}
              {announcement.extraction_confidence === null
                ? "not supplied"
                : `${Math.round(Number(announcement.extraction_confidence) * 100)}%`}
            </span>
          </div>
          <div className="mt-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-muted">
                  Materiality assessment
                </p>
                <p className="mt-1 text-2xl font-semibold tracking-[-0.04em] text-ink tabular">
                  {materiality?.score ?? announcement.materiality_score ?? "—"}
                  <span className="ml-1 text-xs font-medium text-ink-muted">/100</span>
                </p>
              </div>
              <Badge
                className={
                  priorityStyles[
                    materiality?.priority ??
                      (isPriority(announcement.priority) ? announcement.priority : "low")
                  ]
                }
                variant="neutral"
              >
                {materiality?.priority ?? announcement.priority}
              </Badge>
            </div>
            {materiality ? (
              <ul className="mt-3 space-y-2">
                {materiality.reasons.map((reason, index) => (
                  <li className="flex items-start gap-2 text-xs leading-5 text-ink-secondary" key={`${index}-${reason}`}>
                    <Check className="mt-0.5 shrink-0 text-positive" size={13} />
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
            <span className="text-[10px] text-ink-muted">
              Deterministic assessment · explanations from Push API
            </span>
            {sourceIsHttp(announcement.original_filing_url) ? (
              <a
                className="inline-flex min-h-10 items-center gap-2 rounded-md bg-brand px-3 text-xs font-medium text-white hover:bg-brand-strong"
                href={announcement.original_filing_url}
                rel="noreferrer"
                target="_blank"
              >
                Open original filing
                <ExternalLink size={13} />
              </a>
            ) : (
              <span className="text-[10px] text-ink-muted">
                {announcement.is_synthetic
                  ? "Demo fixture · no external filing URL"
                  : "Original filing link is unavailable"}
              </span>
            )}
          </div>
        </>
      ) : null}
    </section>
  );
}

function AlertHistoryCard({
  alert,
  busy,
  disabled,
  onToggleRead,
  onOpenAnnouncement,
}: {
  alert: AlertHistoryItem;
  busy: boolean;
  disabled: boolean;
  onToggleRead: () => void;
  onOpenAnnouncement: () => void;
}) {
  const isUnread = alert.status !== "read";
  return (
    <article className={cn("rounded-md border p-3", isUnread ? "border-brand/20 bg-brand-tint/40" : "border-line bg-white")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-ink">{alert.title}</span>
            <DemoBadge visible={alert.is_synthetic} />
            <Badge variant={isUnread ? "info" : "neutral"}>
              {isUnread ? "Unread" : "Read"}
            </Badge>
          </div>
          <p className="mt-1 text-[11px] text-ink-muted">
            {alert.company_name ?? "Portfolio"} · {formatFiledAt(alert.created_at)} IST
          </p>
          {alert.summary ? (
            <p className="mt-2 line-clamp-3 text-xs leading-5 text-ink-secondary">
              {alert.summary}
            </p>
          ) : null}
        </div>
        {isUnread ? (
          <span aria-label="Unread alert" className="mt-1 size-2 shrink-0 rounded-full bg-brand" />
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {alert.announcement_id ? (
          <Button onClick={onOpenAnnouncement} size="sm" type="button" variant="outline">
            View filing context
            <ChevronRight size={13} />
          </Button>
        ) : null}
        <Button
          disabled={disabled}
          onClick={onToggleRead}
          size="sm"
          type="button"
          variant="ghost"
        >
          {busy ? <LoaderCircle className="animate-spin" size={13} /> : <Check size={13} />}
          Mark {isUnread ? "read" : "unread"}
        </Button>
      </div>
    </article>
  );
}

export function PushWorkspace() {
  const [timeWindow, setTimeWindow] = useState<DigestWindow>("24h");
  const [tickerInput, setTickerInput] = useState("");
  const [tickerFilter, setTickerFilter] = useState("");
  const [categories, setCategories] = useState<AnnouncementCategory[]>([]);
  const [priorities, setPriorities] = useState<Priority[]>([]);
  const [categoryMenuOpen, setCategoryMenuOpen] = useState(false);
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [digest, setDigest] = useState<Announcement[]>([]);
  const [digestTotal, setDigestTotal] = useState(0);
  const [digestError, setDigestError] = useState<string | null>(null);
  const [digestLoading, setDigestLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [alertHistory, setAlertHistory] = useState<AlertHistoryItem[]>([]);
  const [alertError, setAlertError] = useState<string | null>(null);
  const [alertLoading, setAlertLoading] = useState(true);
  const [config, setConfig] = useState<AlertConfiguration | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [configSaving, setConfigSaving] = useState(false);
  const [configSaved, setConfigSaved] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<Announcement | null>(null);
  const [materiality, setMateriality] = useState<Materiality | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [results, setResults] = useState<ResultsComparison | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [statusUpdating, setStatusUpdating] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const detailRequestId = useRef(0);

  const requestFilters = useMemo(() => {
    if (timeWindow === "custom" && (!customStart || !customEnd)) return null;
    return {
      window: timeWindow,
      ticker: tickerFilter || undefined,
      categories,
      priorities,
      start: timeWindow === "custom" ? dateToIso(customStart) : undefined,
      end: timeWindow === "custom" ? dateToIso(customEnd, true) : undefined,
    };
  }, [categories, customEnd, customStart, priorities, tickerFilter, timeWindow]);

  const reloadAlertHistory = useCallback(async () => {
    setAlertLoading(true);
    setAlertError(null);
    try {
      const response = await fetchAlertHistory();
      setAlertHistory(response.alerts);
    } catch (error) {
      setAlertHistory([]);
      setAlertError(error instanceof Error ? error.message : "Alert history could not be loaded.");
    } finally {
      setAlertLoading(false);
    }
  }, []);

  const reloadConfig = useCallback(async () => {
    setConfigLoading(true);
    setConfigError(null);
    try {
      setConfig(await fetchAlertConfiguration());
    } catch (error) {
      setConfig(null);
      setConfigError(error instanceof Error ? error.message : "Alert configuration could not be loaded.");
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!requestFilters) return;
    let active = true;
    void fetchDigest(requestFilters)
      .then((response) => {
        if (!active) return;
        setDigest(response.announcements);
        setDigestTotal(response.total);
        setLastUpdated(new Date());
        setDigestError(null);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setDigest([]);
        setDigestTotal(0);
        setDigestError(error instanceof Error ? error.message : "The portfolio digest could not be loaded.");
      })
      .finally(() => {
        if (active) setDigestLoading(false);
      });
    return () => {
      active = false;
    };
  }, [requestFilters, refreshKey]);

  useEffect(() => {
    let active = true;
    void fetchAlertHistory()
      .then((response) => {
        if (active) {
          setAlertHistory(response.alerts);
          setAlertError(null);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setAlertHistory([]);
          setAlertError(error instanceof Error ? error.message : "Alert history could not be loaded.");
        }
      })
      .finally(() => {
        if (active) setAlertLoading(false);
      });
    void fetchAlertConfiguration()
      .then((response) => {
        if (active) {
          setConfig(response);
          setConfigError(null);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setConfig(null);
          setConfigError(error instanceof Error ? error.message : "Alert configuration could not be loaded.");
        }
      })
      .finally(() => {
        if (active) setConfigLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const tickerChoices = useMemo(() => {
    const unique = new Map<string, string>();
    for (const item of digest) unique.set(item.ticker, item.company_name);
    return Array.from(unique, ([ticker, company]) => ({ ticker, company }));
  }, [digest]);

  const selectedSummary = digest.find((item) => item.id === selectedId) ?? null;
  const currentAnnouncement = selectedDetail ?? selectedSummary;
  const linkedAlert = alertHistory.some(
    (alert) => alert.announcement_id === selectedId,
  );

  useEffect(() => {
    if (!currentAnnouncement?.ticker) {
      return;
    }
    let active = true;
    void fetchResults(currentAnnouncement.ticker)
      .then((response) => {
        if (active) {
          setResults(response);
          setResultsError(null);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setResultsError(
            error instanceof Error ? error.message : "Quarterly financial data could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (active) setResultsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [currentAnnouncement?.ticker, refreshKey]);

  function applyCompanySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTickerFilter(tickerInput.trim().toUpperCase().replace(/\.NS$/, ""));
    setSelectedId(null);
    setSelectedDetail(null);
    setResults(null);
    setResultsError(null);
    beginDigestRefresh();
  }

  function beginDigestRefresh() {
    setDigestLoading(Boolean(requestFilters));
    setDigestError(null);
  }

  function toggleCategory(category: AnnouncementCategory) {
    beginDigestRefresh();
    setCategories((current) =>
      current.includes(category)
        ? current.filter((value) => value !== category)
        : [...current, category],
    );
  }

  function togglePriority(priority: Priority) {
    beginDigestRefresh();
    setPriorities((current) =>
      current.includes(priority)
        ? current.filter((value) => value !== priority)
        : [...current, priority],
    );
  }

  function clearFilters() {
    setDigestLoading(true);
    setDigestError(null);
    setTickerInput("");
    setTickerFilter("");
    setCategories([]);
    setPriorities([]);
    setTimeWindow("24h");
    setCustomStart("");
    setCustomEnd("");
  }

  async function selectAnnouncement(id: string) {
    setSelectedId(id);
    setSelectedDetail(null);
    setMateriality(null);
    setDetailLoading(true);
    setDetailError(null);
    setResults(null);
    setResultsError(null);
    setResultsLoading(true);
    const requestId = ++detailRequestId.current;
    const [detailResult, materialityResult] = await Promise.allSettled([
      fetchAnnouncement(id),
      fetchMateriality(id),
    ]);
    if (requestId !== detailRequestId.current) return;
    if (detailResult.status === "fulfilled") setSelectedDetail(detailResult.value);
    else setDetailError(detailResult.reason instanceof Error ? detailResult.reason.message : "Announcement details could not be loaded.");
    if (materialityResult.status === "fulfilled") setMateriality(materialityResult.value);
    else if (!detailError) setDetailError(materialityResult.reason instanceof Error ? materialityResult.reason.message : "Materiality explanation could not be loaded.");
    setDetailLoading(false);
    globalThis.setTimeout(() => {
      document.getElementById("announcement-detail")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }, 0);
  }

  async function toggleAlertStatus(alert: AlertHistoryItem) {
    if (statusUpdating !== null) return;
    setStatusUpdating(alert.id);
    try {
      const updated = await updateAlertStatus(
        alert.id,
        alert.status === "read" ? "unread" : "read",
      );
      setAlertHistory((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (error) {
      setAlertError(error instanceof Error ? error.message : "Alert status could not be updated.");
    } finally {
      setStatusUpdating(null);
    }
  }

  async function saveConfiguration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config) return;
    setConfigSaving(true);
    setConfigSaved(false);
    setConfigError(null);
    try {
      const saved = await saveAlertConfiguration({
        ticker: config.ticker,
        enabled: config.enabled,
        price_move_threshold_pct: config.price_move_threshold_pct,
        volume_ratio_threshold: config.volume_ratio_threshold,
        categories: config.categories,
        minimum_materiality_score: config.minimum_materiality_score,
      });
      setConfig(saved);
      setConfigSaved(true);
    } catch (error) {
      setConfigError(error instanceof Error ? error.message : "Alert preferences could not be saved.");
    } finally {
      setConfigSaving(false);
    }
  }

  const unreadCount = alertHistory.filter((alert) => alert.status !== "read").length;
  const demoAnnouncementCount = digest.filter((item) => item.is_synthetic).length;

  return (
    <div className="mx-auto w-full max-w-[1480px] px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
      <header className="mb-5 border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
              Push · Portfolio signals
            </p>
            <h1 className="text-[25px] font-semibold tracking-[-0.045em] text-ink sm:text-[29px]">
              Push intelligence
            </h1>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-ink-secondary sm:text-sm">
              Filings, materiality, and portfolio alerts in one review workflow.
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2">
            <span className={cn("size-2 rounded-full", digestError ? "bg-negative" : "bg-positive")} />
            <span className="text-[11px] font-medium text-ink-secondary">
              {digestError ? "API issue" : "Connected to Push API"}
            </span>
            {demoAnnouncementCount > 0 ? (
              <Badge variant="caution">{demoAnnouncementCount} demo</Badge>
            ) : null}
          </div>
        </div>
      </header>

      <nav
        aria-label="Push review workflow"
        className="mb-5 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-line bg-surface px-3 py-2.5 text-[10px] font-medium text-ink-muted sm:px-4"
      >
        <a className="hover:text-brand" href="#portfolio-digest">Portfolio</a>
        <ChevronRight size={12} />
        <a className="hover:text-brand" href="#portfolio-digest">Announcement</a>
        <ChevronRight size={12} />
        <a className="hover:text-brand" href="#materiality">Materiality</a>
        <ChevronRight size={12} />
        <a className="hover:text-brand" href="#materiality">Explanation</a>
        <ChevronRight size={12} />
        <a className="hover:text-brand" href="#alert-history">Alert</a>
      </nav>

      <section
        aria-labelledby="portfolio-digest-title"
        className="rounded-lg border border-line bg-surface p-4 sm:p-5"
        id="portfolio-digest"
      >
        <SectionHeading
          action={
            <div className="flex items-center gap-2">
              {lastUpdated ? (
                <span className="hidden text-[10px] text-ink-muted sm:inline">
                  Updated {lastUpdated.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                </span>
              ) : null}
              <Button
                disabled={digestLoading || !requestFilters}
                onClick={() => {
                  setRefreshing(true);
                  beginDigestRefresh();
                  setRefreshKey((value) => value + 1);
                  const refreshTasks = [reloadAlertHistory(), reloadConfig()];
                  if (selectedId) refreshTasks.push(selectAnnouncement(selectedId));
                  void Promise.all(refreshTasks).finally(() => setRefreshing(false));
                }}
                size="sm"
                type="button"
                variant="outline"
              >
                <RefreshCw className={cn((digestLoading || refreshing) && "animate-spin")} size={14} />
                Refresh
              </Button>
            </div>
          }
          description="Start with the portfolio-wide filing stream, then inspect the reason behind each score."
          eyebrow="01 · Portfolio"
          step="1"
          title="Announcement digest"
        />

        <form
          className="mt-5 grid gap-3 border-t border-line pt-4 sm:grid-cols-2 xl:grid-cols-[minmax(210px,1.3fr)_150px_minmax(250px,1.5fr)_minmax(230px,1.2fr)_auto]"
          onSubmit={applyCompanySearch}
        >
          <label className="block">
            <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Company / ticker
            </span>
            <span className="flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3 focus-within:border-brand/50">
              <Search className="shrink-0 text-ink-muted" size={14} />
              <input
                aria-label="Search company or ticker"
                autoComplete="off"
                className="min-w-0 flex-1 bg-transparent text-xs text-ink outline-none placeholder:text-ink-muted"
                list="push-company-options"
                onChange={(event) => setTickerInput(event.target.value)}
                placeholder="e.g. RELIANCE"
                value={tickerInput}
              />
              <datalist id="push-company-options">
                {tickerChoices.map(({ ticker, company }) => (
                  <option key={ticker} value={ticker}>{company}</option>
                ))}
              </datalist>
            </span>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Time window
            </span>
            <select
              aria-label="Announcement time window"
              className="h-10 w-full rounded-md border border-line bg-white px-3 text-xs font-medium text-ink outline-none focus:border-brand/50"
              onChange={(event) => {
                const nextWindow = event.target.value as DigestWindow;
                setTimeWindow(nextWindow);
                setDigestError(null);
                if (nextWindow === "custom" && (!customStart || !customEnd)) {
                  setDigestLoading(false);
                } else {
                  setDigestLoading(true);
                }
              }}
              value={timeWindow}
            >
              <option value="24h">Last 24 hours</option>
              <option value="48h">Last 48 hours</option>
              <option value="7d">Last 7 days</option>
              <option value="custom">Custom dates</option>
            </select>
          </label>

          <fieldset className="min-w-0">
            <legend className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Category
            </legend>
            <details
              className="group relative"
              onToggle={(event) => setCategoryMenuOpen(event.currentTarget.open)}
              open={categoryMenuOpen}
            >
              <summary className="flex h-10 cursor-pointer list-none items-center justify-between rounded-md border border-line bg-white px-3 text-xs font-medium text-ink-secondary">
                <span className="inline-flex items-center gap-2">
                  <Filter size={13} />
                  {categories.length ? `${categories.length} selected` : "All categories"}
                </span>
                <ChevronRight className="rotate-90 transition-transform group-open:-rotate-90" size={13} />
              </summary>
              <div className="absolute left-0 right-0 top-11 z-10 max-h-64 overflow-auto rounded-md border border-line bg-white p-2 shadow-lg sm:min-w-[280px]">
                {announcementCategories.map((category) => (
                  <label
                    className="flex min-h-9 cursor-pointer items-center gap-2 rounded px-2 text-xs text-ink-secondary hover:bg-surface-muted"
                    key={category}
                  >
                    <input
                      checked={categories.includes(category)}
                      className="accent-brand"
                      onChange={() => {
                        toggleCategory(category);
                        setCategoryMenuOpen(false);
                      }}
                      type="checkbox"
                    />
                    {category}
                  </label>
                ))}
              </div>
            </details>
          </fieldset>

          <fieldset className="min-w-0">
            <legend className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Priority
            </legend>
            <div className="flex h-10 flex-wrap items-center gap-1.5">
              {(["critical", "high", "medium", "low"] as const).map((priority) => (
                <button
                  aria-pressed={priorities.includes(priority)}
                  className={cn(
                    "min-h-8 rounded-full border px-2 text-[10px] font-semibold capitalize transition-colors",
                    priorities.includes(priority)
                      ? priorityStyles[priority]
                      : "border-line bg-white text-ink-muted hover:text-ink",
                  )}
                  key={priority}
                  onClick={() => togglePriority(priority)}
                  type="button"
                >
                  {priority}
                </button>
              ))}
            </div>
          </fieldset>

          {timeWindow === "custom" ? (
            <div className="grid grid-cols-2 gap-2 sm:col-span-2 xl:col-span-5">
              <label className="text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
                From
                <input
                  aria-label="Custom start date"
                  className="mt-1 block h-10 w-full rounded-md border border-line bg-white px-3 text-xs font-normal text-ink"
                  onChange={(event) => {
                    setCustomStart(event.target.value);
                    setDigestLoading(Boolean(event.target.value && customEnd));
                    setDigestError(null);
                  }}
                  type="date"
                  value={customStart}
                />
              </label>
              <label className="text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
                To
                <input
                  aria-label="Custom end date"
                  className="mt-1 block h-10 w-full rounded-md border border-line bg-white px-3 text-xs font-normal text-ink"
                  onChange={(event) => {
                    setCustomEnd(event.target.value);
                    setDigestLoading(Boolean(customStart && event.target.value));
                    setDigestError(null);
                  }}
                  type="date"
                  value={customEnd}
                />
              </label>
            </div>
          ) : null}
          {timeWindow === "custom" && (!customStart || !customEnd) ? (
            <p className="text-xs text-caution sm:col-span-2 xl:col-span-5" role="status">
              Choose both dates to apply a custom window.
            </p>
          ) : null}
          <div className="flex items-end gap-2 sm:col-span-2 xl:col-span-5">
            <Button className="flex-1 sm:flex-none" type="submit" size="sm">
              Apply company search
            </Button>
            <Button onClick={clearFilters} type="button" size="sm" variant="ghost">
              Clear filters
            </Button>
            {(tickerFilter || categories.length || priorities.length) ? (
              <span className="ml-auto hidden items-center gap-1 text-[10px] text-ink-muted sm:inline-flex">
                <SlidersHorizontal size={12} />
                Filtered view
              </span>
            ) : null}
          </div>
        </form>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-[10px] text-ink-muted">
          <span>
            {digestLoading ? "Refreshing portfolio announcements…" : `${digestTotal} matching filing${digestTotal === 1 ? "" : "s"}`}
            {tickerFilter ? ` · ${tickerFilter}` : " · Portfolio-wide"}
          </span>
          <span className="inline-flex items-center gap-1">
            <ShieldCheck size={12} />
            Exchange filing times shown in IST
          </span>
        </div>

        {digestError ? (
          <div className="mt-4">
            <ErrorState message={digestError} onRetry={() => setRefreshKey((value) => value + 1)} />
          </div>
        ) : digestLoading ? (
          <div className="mt-4 grid gap-3 lg:grid-cols-2" aria-label="Loading announcement digest" role="status">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : digest.length === 0 ? (
          <div className="mt-4 rounded-lg border border-dashed border-line bg-canvas/70 px-4 py-9 text-center">
            <span className="mx-auto flex size-10 items-center justify-center rounded-full bg-brand-tint text-brand">
              <Bell size={17} />
            </span>
            <h3 className="mt-3 text-sm font-semibold text-ink">No filings match this view</h3>
            <p className="mx-auto mt-1 max-w-lg text-xs leading-5 text-ink-secondary">
              This is the backend response for the selected portfolio and filters. Widen the time window or clear filters; FINN does not substitute sample filings.
            </p>
            <Button className="mt-4" onClick={clearFilters} size="sm" type="button" variant="outline">
              Clear filters
            </Button>
          </div>
        ) : (
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {digest.map((announcement) => (
              <AnnouncementCard
                announcement={announcement}
                key={announcement.id}
                onSelect={() => void selectAnnouncement(announcement.id)}
                relatedAlert={alertHistory.some((alert) => alert.announcement_id === announcement.id)}
                selected={announcement.id === selectedId}
              />
            ))}
          </div>
        )}
      </section>

      <div className="mt-4 grid items-start gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
        <div className="space-y-4">
          <div id="materiality">
            <SectionHeading
              description="Inspect the source filing and every rule contributing to its score."
              eyebrow="02–03 · Filing → materiality"
              step="2"
              title="Announcement & why it matters"
            />
            <div className="mt-3">
              <AnnouncementDetail
                alertLinked={linkedAlert}
                announcement={currentAnnouncement}
                error={detailError}
                loading={detailLoading}
                materiality={materiality}
                onClose={() => {
                  detailRequestId.current += 1;
                  setSelectedId(null);
                  setSelectedDetail(null);
                  setMateriality(null);
                  setDetailError(null);
                }}
              />
            </div>
            {currentAnnouncement?.category === "management_change" ? (
              <div className="mt-3">
                <NetworkRecommendationsPanel
                  compact
                  ticker={currentAnnouncement.ticker}
                  title="Reachable contacts for management diligence"
                  workflow="management_diligence"
                />
              </div>
            ) : null}
          </div>

          <section aria-labelledby="results-title" className="rounded-lg border border-line bg-surface p-4 sm:p-5">
            <SectionHeading
              eyebrow="04 · Quarterly source comparison"
              step="4"
              title={results ? `${results.company_name} · ${results.current_period}` : "Quarterly financial highlights"}
              description={
                currentAnnouncement
                  ? `${currentAnnouncement.ticker} · ${results?.reporting_basis ?? "Reporting basis from source"}`
                  : "Select an announcement to load its issuer's reported quarterly metrics."
              }
            />
            {resultsLoading ? (
              <div className="mt-4 grid gap-2 sm:grid-cols-2" role="status" aria-label="Loading quarterly metrics">
                {Array.from({ length: 4 }, (_, index) => (
                  <div className="h-32 animate-pulse rounded-md border border-line bg-surface-muted/60" key={index} />
                ))}
              </div>
            ) : resultsError ? (
              <div className="mt-4 rounded-md border border-line bg-canvas p-3">
                <p className="text-xs font-semibold text-ink">No quarterly highlights available</p>
                <p className="mt-1 text-xs leading-5 text-ink-secondary">{resultsError}</p>
              </div>
            ) : results ? (
              <>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge variant="neutral">{results.reporting_basis}</Badge>
                  <Badge variant="neutral">{results.currency} · {results.unit_scale}</Badge>
                  <span className="text-[10px] text-ink-muted">
                    QoQ = prior quarter · YoY = same quarter one year earlier
                  </span>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {results.metrics.map((metric) => (
                    <MetricTile key={metric.metric_key} metric={metric} results={results} />
                  ))}
                </div>
                <p className="mt-3 flex items-start gap-2 text-[10px] leading-4 text-ink-muted">
                  <CircleHelp className="mt-0.5 shrink-0" size={12} />
                  Missing values remain blank; percentage changes are withheld for zero or negative comparison bases.
                </p>
              </>
            ) : (
              <div className="mt-4 rounded-md border border-dashed border-line px-3 py-5 text-center text-xs text-ink-muted">
                Quarterly metrics appear here after selecting an issuer filing.
              </div>
            )}
          </section>
        </div>

        <aside className="space-y-4">
          <section aria-labelledby="alert-config-title" className="rounded-lg border border-line bg-surface p-4 sm:p-5">
            <SectionHeading
              description="Persist category and end-of-day thresholds for this workspace."
              eyebrow="05 · Alert rules"
              step="5"
              title="Alert configuration"
            />
            {configLoading ? (
              <div className="mt-4 space-y-3" aria-label="Loading alert rules" role="status">
                <div className="h-9 animate-pulse rounded bg-surface-muted" />
                <div className="h-9 animate-pulse rounded bg-surface-muted" />
                <div className="h-20 animate-pulse rounded bg-surface-muted" />
              </div>
            ) : configError ? (
              <div className="mt-4">
                <ErrorState message={configError} onRetry={() => void reloadConfig()} />
              </div>
            ) : config ? (
              <form className="mt-4 space-y-4" onSubmit={(event) => void saveConfiguration(event)}>
                <label className="flex min-h-10 items-center justify-between gap-3 rounded-md border border-line bg-canvas px-3">
                  <span className="text-xs font-medium text-ink">Rules enabled</span>
                  <input
                    aria-label="Enable alert rules"
                    checked={config.enabled}
                    className="size-4 accent-brand"
                    onChange={(event) => setConfig({ ...config, enabled: event.target.checked })}
                    type="checkbox"
                  />
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-[10px] font-semibold text-ink-secondary">
                    EOD price move (%)
                    <input
                      className="mt-1 h-10 w-full rounded-md border border-line bg-white px-3 text-xs font-normal text-ink"
                      max="100"
                      min="0.01"
                      onChange={(event) => setConfig({ ...config, price_move_threshold_pct: event.target.value || null })}
                      step="0.01"
                      type="number"
                      value={config.price_move_threshold_pct ?? ""}
                    />
                  </label>
                  <label className="text-[10px] font-semibold text-ink-secondary">
                    Volume multiple
                    <input
                      className="mt-1 h-10 w-full rounded-md border border-line bg-white px-3 text-xs font-normal text-ink"
                      max="100"
                      min="0.01"
                      onChange={(event) => setConfig({ ...config, volume_ratio_threshold: event.target.value || null })}
                      step="0.01"
                      type="number"
                      value={config.volume_ratio_threshold ?? ""}
                    />
                  </label>
                </div>
                <label className="block text-[10px] font-semibold text-ink-secondary">
                  Minimum materiality score
                  <input
                    className="mt-1 h-10 w-full rounded-md border border-line bg-white px-3 text-xs font-normal text-ink"
                    max="100"
                    min="0"
                    onChange={(event) =>
                      setConfig({
                        ...config,
                        minimum_materiality_score: event.target.value ? Number(event.target.value) : null,
                      })
                    }
                    step="1"
                    type="number"
                    value={config.minimum_materiality_score ?? ""}
                  />
                </label>
                <fieldset>
                  <legend className="mb-2 text-[10px] font-semibold text-ink-secondary">
                    Announcement categories
                  </legend>
                  <div className="flex flex-wrap gap-1.5">
                    {announcementCategories.map((category) => (
                      <label className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-full border border-line bg-white px-2 text-[10px] text-ink-secondary" key={category}>
                        <input
                          checked={config.categories.includes(category)}
                          className="accent-brand"
                          onChange={(event) =>
                            setConfig({
                              ...config,
                              categories: event.target.checked
                                ? [...config.categories, category]
                                : config.categories.filter((item) => item !== category),
                            })
                          }
                          type="checkbox"
                        />
                        {category}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div className="flex flex-wrap items-center gap-2">
                  <Button disabled={configSaving} size="sm" type="submit">
                    {configSaving ? <LoaderCircle className="animate-spin" size={14} /> : <Check size={14} />}
                    Save alert rules
                  </Button>
                  {configSaved ? (
                    <span className="text-[10px] font-medium text-positive" role="status">Saved to backend</span>
                  ) : null}
                </div>
                <p className="text-[10px] leading-4 text-ink-muted">
                  Price and volume conditions are evaluated on end-of-day data. Volume requires {config.volume_lookback_sessions} earlier trading sessions.
                </p>
                {configError ? <p className="text-xs text-negative" role="alert">{configError}</p> : null}
              </form>
            ) : null}
          </section>

          <section
            aria-labelledby="alert-history-title"
            className="rounded-lg border border-line bg-surface p-4 sm:p-5"
            id="alert-history"
          >
            <SectionHeading
              action={
                <Badge variant={unreadCount ? "info" : "neutral"}>
                  {unreadCount} unread
                </Badge>
              }
              description="Persisted alert events; read state is saved through the API."
              eyebrow="06 · Prioritized response"
              step="6"
              title="Alert history"
            />
            {alertError ? (
              <div className="mt-4">
                <ErrorState message={alertError} onRetry={() => void reloadAlertHistory()} />
              </div>
            ) : alertLoading ? (
              <div className="mt-4 space-y-2" role="status" aria-label="Loading alert history">
                <div className="h-24 animate-pulse rounded-md bg-surface-muted" />
                <div className="h-24 animate-pulse rounded-md bg-surface-muted" />
              </div>
            ) : alertHistory.length === 0 ? (
              <div className="mt-4 rounded-md border border-dashed border-line px-3 py-6 text-center">
                <Bell className="mx-auto text-ink-muted" size={17} />
                <p className="mt-2 text-xs font-medium text-ink">No alerts have been recorded</p>
                <p className="mt-1 text-[10px] leading-4 text-ink-muted">
                  Alerts appear here after a backend rule matches an announcement or EOD market observation.
                </p>
              </div>
            ) : (
              <div className="mt-4 space-y-2">
                {alertHistory.map((alert) => (
                  <AlertHistoryCard
                    alert={alert}
                    busy={statusUpdating === alert.id}
                    disabled={statusUpdating !== null}
                    key={alert.id}
                    onOpenAnnouncement={() => {
                      if (alert.announcement_id) void selectAnnouncement(alert.announcement_id);
                    }}
                    onToggleRead={() => void toggleAlertStatus(alert)}
                  />
                ))}
              </div>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
