import { accessTokenHeaders } from "@/lib/session-auth";

export const announcementCategories = [
  "results",
  "M&A",
  "fund_raise",
  "management_change",
  "litigation",
  "insider_trading",
  "earnings_call",
  "investor_meetings",
  "credit_rating",
  "dividend",
  "bonus_split",
  "capex",
  "press_release",
  "postal_ballot",
  "agm_egm",
  "pledging",
  "unclassified",
] as const;

export type AnnouncementCategory = (typeof announcementCategories)[number];
export type Priority = "critical" | "high" | "medium" | "low";
export type DigestWindow = "24h" | "48h" | "7d" | "custom";

export type Announcement = {
  id: string;
  company_name: string;
  ticker: string;
  headline: string;
  filed_at: string;
  category: AnnouncementCategory;
  summary: string;
  original_filing_url: string;
  extraction_confidence: number | null;
  source_metadata: Record<string, unknown>;
  materiality_score: number | null;
  priority: Priority;
  materiality_reasons: string[];
  is_synthetic: boolean;
  network_context: Array<{
    person_id: string;
    display_name: string;
    role: string | null;
    organization: string;
    match_reason: string;
    synthetic: boolean;
  }>;
};

export type AnnouncementDigest = {
  start: string;
  end: string;
  total: number;
  announcements: Announcement[];
};

export type Materiality = {
  announcement_id: string;
  score: number;
  priority: Priority;
  reasons: string[];
};

export type AlertConfiguration = {
  workspace_id: string;
  ticker: string | null;
  enabled: boolean;
  price_move_threshold_pct: string | null;
  volume_ratio_threshold: string | null;
  categories: AnnouncementCategory[];
  minimum_materiality_score: number | null;
  volume_lookback_sessions: number;
};

export type AlertHistoryItem = {
  id: string;
  company_name: string | null;
  alert_type: string;
  title: string;
  summary: string | null;
  status: "read" | "unread" | string;
  created_at: string;
  announcement_id: string | null;
  dedupe_key: string;
  is_synthetic: boolean;
};

export type AlertHistory = {
  workspace_id: string;
  total: number;
  alerts: AlertHistoryItem[];
};

export type PeriodValue = {
  value: string | null;
  period_label: string | null;
  period_end: string | null;
  currency: string | null;
  unit_scale: string | null;
  reporting_basis: string | null;
  source_url: string | null;
  is_synthetic: boolean;
  reason: string | null;
};

export type FinancialMetricComparison = {
  metric_key: "revenue" | "ebitda" | "pbt" | "pat";
  current: PeriodValue;
  qoq: PeriodValue;
  yoy: PeriodValue;
  qoq_absolute_change: string | null;
  qoq_percent_change: string | null;
  qoq_change_note: string | null;
  yoy_absolute_change: string | null;
  yoy_percent_change: string | null;
  yoy_change_note: string | null;
};

export type ResultsComparison = {
  ticker: string;
  company_name: string;
  reporting_basis: string;
  currency: string;
  unit_scale: string;
  current_period: string;
  metrics: FinancialMetricComparison[];
};

export class PushApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "PushApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/push/${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...accessTokenHeaders(),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const body = payload as
      | { detail?: { message?: string }; error?: { message?: string } }
      | null;
    const message =
      body?.detail?.message ??
      body?.error?.message ??
      `Push API request failed (${response.status}).`;
    throw new PushApiError(message, response.status);
  }
  return payload as T;
}

export async function fetchDigest(filters: {
  window: DigestWindow;
  ticker?: string;
  categories: AnnouncementCategory[];
  priorities: Priority[];
  start?: string;
  end?: string;
}): Promise<AnnouncementDigest> {
  const params = new URLSearchParams({ window: filters.window });
  if (filters.ticker) params.append("ticker", filters.ticker);
  for (const category of filters.categories) params.append("category", category);
  for (const priority of filters.priorities) params.append("priority", priority);
  if (filters.window === "custom" && filters.start && filters.end) {
    params.set("start", filters.start);
    params.set("end", filters.end);
  }
  return request(`digest?${params.toString()}`);
}

export function fetchAnnouncement(id: string): Promise<Announcement> {
  return request(`announcements/${encodeURIComponent(id)}`);
}

export function fetchMateriality(id: string): Promise<Materiality> {
  return request(`announcements/${encodeURIComponent(id)}/materiality`);
}

export function fetchResults(ticker: string): Promise<ResultsComparison> {
  return request(`results/${encodeURIComponent(ticker)}/comparisons`);
}

export function fetchAlertConfiguration(
  ticker?: string,
): Promise<AlertConfiguration> {
  const params = new URLSearchParams();
  if (ticker) params.set("ticker", ticker);
  return request(`alerts/config${params.size ? `?${params.toString()}` : ""}`);
}

export function saveAlertConfiguration(
  config: Omit<AlertConfiguration, "workspace_id" | "volume_lookback_sessions">,
): Promise<AlertConfiguration> {
  return request("alerts/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export function fetchAlertHistory(): Promise<AlertHistory> {
  return request("alerts/history");
}

export function updateAlertStatus(
  alertId: string,
  status: "read" | "unread",
): Promise<AlertHistoryItem> {
  return request(`alerts/${encodeURIComponent(alertId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}
