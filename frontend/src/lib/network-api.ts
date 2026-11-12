import { accessTokenHeaders } from "@/lib/session-auth";

export type NetworkExperience = {
  organization: string;
  title: string | null;
  sector: string | null;
  start_date: string | null;
  end_date: string | null;
  ticker: string | null;
  is_current: boolean;
  is_synthetic: boolean;
};

export type NetworkEducation = {
  institution: string;
  qualification: string | null;
  field_of_study: string | null;
  graduation_year: number | null;
  is_synthetic: boolean;
};

export type NetworkPathStep = {
  contact_id: string;
  name: string;
  relationship_type: string;
  strength: string | null;
  evidence: string | null;
  last_interaction: string | null;
};

export type NetworkContact = {
  id: string;
  display_name: string;
  current_role: string | null;
  current_employer: string | null;
  previous_employers: string[];
  education: NetworkEducation[];
  graduation_year: number | null;
  expertise: string[];
  industry_experience: string[];
  companies_worked_with: string[];
  connection_type: string | null;
  connection_distance: 1 | 2 | null;
  last_interaction: string | null;
  relationship_strength: string | null;
  relationship_evidence: string | null;
  relationship_path: NetworkPathStep[];
  is_synthetic: boolean;
  experiences: NetworkExperience[];
};

export type NetworkContactSearch = {
  total: number;
  contacts: NetworkContact[];
};

export type NetworkRecommendation = {
  contact: NetworkContact;
  score: number;
  connection_distance: 1 | 2;
  reasons: string[];
  path: NetworkPathStep[];
  evidence_quality: "explicit_synthetic_fixture" | "explicit_record";
  workflow: "who_to_call" | "second_degree_reach" | "management_diligence" | "sector_expertise" | "keep_warm";
};

export type NetworkRecommendations = {
  workflow: NetworkRecommendation["workflow"];
  ticker: string | null;
  executive: string | null;
  recommendations: NetworkRecommendation[];
  notice: string;
};

export type CompanyConnections = {
  ticker: string;
  company_name: string;
  contacts: NetworkContact[];
  match_confidence: number;
  match_evidence: string[];
  entity_matches: Array<{
    contact_id: string;
    contact_name: string;
    confidence: number;
    status: "accepted" | "proposed";
    method: string;
    evidence: string;
  }>;
};

export class NetworkApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "NetworkApiError";
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`/api/network/${path}`, {
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...accessTokenHeaders(),
    },
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const body = payload as
      | { error?: { message?: string }; detail?: { message?: string } }
      | null;
    throw new NetworkApiError(
      body?.error?.message ??
        body?.detail?.message ??
        `Network request failed (${response.status}).`,
      response.status,
    );
  }
  return payload as T;
}

function params(values: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && String(value).trim()) search.set(key, String(value));
  }
  return search.toString();
}

export function searchNetworkContacts(query?: string): Promise<NetworkContactSearch> {
  return request(`contacts?${params({ q: query, limit: 50 })}`);
}

export function searchNetworkExpertise(query: string): Promise<NetworkContactSearch> {
  return request(`expertise?${params({ q: query, limit: 50 })}`);
}

export function fetchCompanyConnections(ticker: string): Promise<CompanyConnections> {
  return request(`companies/${encodeURIComponent(ticker)}/connections?${params({})}`);
}

export function fetchNetworkRecommendations(options: {
  workflow: NetworkRecommendation["workflow"];
  ticker?: string;
  executive?: string;
  expertise?: string;
  limit?: number;
}): Promise<NetworkRecommendations> {
  return request(`recommendations?${params(options)}`);
}

export function fetchRelationshipPath(contactId: string): Promise<{
  contact_id: string;
  distance: 1 | 2 | null;
  path: NetworkPathStep[];
  explanation: string;
}> {
  return request(`paths/${encodeURIComponent(contactId)}?${params({})}`);
}
