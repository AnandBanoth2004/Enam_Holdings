import { accessTokenHeaders } from "@/lib/session-auth";

export type CompanySearchItem = {
  ticker: string;
  exchange: string;
  company_id: string;
  company_name: string;
  sector: string | null;
  has_primary_documents: boolean;
  has_financial_data: boolean;
};

export type ResearchCitation = {
  document_id: string;
  document_name: string;
  document_type: string;
  reporting_period: string | null;
  page_number: number | null;
  source_url: string;
  quote: string | null;
  chunk_id: string | null;
  is_synthetic: boolean;
};

export type ResearchClaim = {
  text: string;
  claim_type: "reported_fact" | "calculation" | "interpretation";
  citations: ResearchCitation[];
  metric_key?: string | null;
  value?: string | null;
  currency?: string | null;
  unit_scale?: string | null;
  period_label?: string | null;
  reporting_basis?: string | null;
  from_period?: string | null;
  to_period?: string | null;
};

export type ResearchGuidanceRow = {
  statement_date: string | null;
  quarter: string;
  management_statement: string;
  metric_key: string | null;
  expected_result: string | null;
  actual_result: string | null;
  variance: string | null;
  assessment: "exceeded" | "met" | "missed" | "not_yet_verifiable";
  citations: ResearchCitation[];
};

export type ResearchSection = {
  status: "ready" | "partial" | "unavailable";
  facts: ResearchClaim[];
  calculations: ResearchClaim[];
  interpretations: ResearchClaim[];
  observations: Array<Record<string, unknown>>;
  limitations: string[];
  source_references?: ResearchCitation[];
};

export type FinancialResearchReport = {
  report_id: string | null;
  ticker: string;
  company_name: string;
  generated_at: string;
  status: "complete" | "partial" | "unavailable";
  source_count: number;
  source_manifest: ResearchCitation[];
  model_route: string;
  is_synthetic: boolean;
  business_snapshot: ResearchSection;
  financial_snapshot: ResearchSection;
  financial_trajectory: ResearchSection;
  balance_sheet_analysis: ResearchSection;
  cash_quality_analysis: ResearchSection;
  narrative_vs_numbers: ResearchSection;
  management_guidance: ResearchSection;
  bull_vs_bear: ResearchSection;
};

export type ResearchDocument = {
  id: string;
  document_type: "annual_report" | "quarterly_result" | "earnings_call_transcript" | "investor_presentation";
  title: string;
  source_url: string;
  period_label: string | null;
  ingestion_status: string;
  is_primary_source: boolean;
  is_synthetic: boolean;
};

export type ResearchDiscovery = {
  ticker: string;
  company_name: string;
  status: string;
  fetched_at: string;
  error_code: string | null;
  documents: ResearchDocument[];
};

export type IngestionResult = {
  document_id: string;
  status: string;
  duplicate_of: string | null;
  page_count: number;
  chunk_count: number;
  embedded_chunk_count: number;
  embedding_model: string | null;
  extraction_method: string | null;
  period_label: string | null;
};

export type FinancialMetricValue = {
  value: string;
  currency: string;
  unit_scale: string;
  source_page: number | null;
  source_url: string;
  source_excerpt: string | null;
  metric_id: string;
};

export type FinancialPeriod = {
  period_id: string;
  period_label: string;
  period_start: string;
  period_end: string;
  period_type: string;
  reporting_basis: string;
  currency: string;
  unit_scale: string;
  document_id: string;
  document_name: string;
  source_url: string;
  metrics: Record<string, FinancialMetricValue>;
};

export class ResearchApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ResearchApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/research/${path}`, {
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
      | {
          detail?: { message?: string };
          error?: { message?: string };
        }
      | null;
    throw new ResearchApiError(
      body?.detail?.message ??
        body?.error?.message ??
        `Research request failed (${response.status}).`,
      response.status,
    );
  }
  return payload as T;
}

export function searchCompanies(query: string): Promise<{ query: string; results: CompanySearchItem[] }> {
  const params = new URLSearchParams({ q: query, limit: "8" });
  return request(`companies/search?${params.toString()}`);
}

export function discoverCompany(ticker: string): Promise<ResearchDiscovery> {
  return request("discover", {
    method: "POST",
    body: JSON.stringify({ ticker }),
  });
}

export function ingestDocument(documentId: string): Promise<IngestionResult> {
  return request(`documents/${encodeURIComponent(documentId)}/ingest`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function extractDocumentFinancials(
  documentId: string,
  requestBody: {
    period_label: string;
    period_start: string;
    period_end: string;
    period_type: "year" | "quarter";
    reporting_basis: "standalone" | "consolidated";
    currency: string;
    unit_scale: string;
  },
): Promise<{ extracted_count: number; ambiguous_metric_keys: string[]; metric_keys: string[] }> {
  return request(`documents/${encodeURIComponent(documentId)}/extract-financials`, {
    method: "POST",
    body: JSON.stringify(requestBody),
  });
}

export function fetchFinancialPeriods(
  ticker: string,
  reportingBasis: "standalone" | "consolidated",
): Promise<{ ticker: string; reporting_basis: string; periods: FinancialPeriod[] }> {
  return request(
    `companies/${encodeURIComponent(ticker)}/financial-metrics?reporting_basis=${reportingBasis}`,
  );
}

export function generateFinancialReport(
  ticker: string,
  reportingBasis: "standalone" | "consolidated",
): Promise<FinancialResearchReport> {
  return request(`companies/${encodeURIComponent(ticker)}/report`, {
    method: "POST",
    body: JSON.stringify({ reporting_basis: reportingBasis, quarters: 4 }),
  });
}
