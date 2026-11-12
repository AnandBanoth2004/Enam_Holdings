import { accessTokenHeaders } from "@/lib/session-auth";

export type CopilotCitation = {
  source_type: "filing" | "research_document" | "market_data" | "relationship" | "alert";
  title: string;
  source_url: string | null;
  ticker: string | null;
  reporting_period: string | null;
  page_number: number | null;
  quote: string | null;
  is_synthetic: boolean;
};

export type CopilotBlock = {
  layer: "push" | "pull" | "network";
  heading: string;
  summary: string;
  data: Record<string, unknown>;
  citations: CopilotCitation[];
};

export type CopilotTool = {
  name: string;
  status: "complete" | "partial" | "unavailable";
  message: string;
};

export type CopilotResponse = {
  conversation_id: string;
  message_id: string;
  query: string;
  intent: string;
  layers: Array<"push" | "pull" | "network">;
  answer: string;
  blocks: CopilotBlock[];
  tools: CopilotTool[];
  limitations: string[];
  created_at: string;
};

export type CopilotConversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string | null;
};

export type CopilotMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  result: CopilotResponse | null;
  created_at: string;
};

export class CopilotApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "CopilotApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/copilot/${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...accessTokenHeaders(),
      ...init?.headers,
    },
  });
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const body = payload as
      | { error?: { message?: string }; detail?: { message?: string } }
      | null;
    throw new CopilotApiError(
      body?.error?.message ?? body?.detail?.message ?? `Copilot request failed (${response.status}).`,
      response.status,
    );
  }
  return payload as T;
}

export async function listCopilotConversations(): Promise<CopilotConversation[]> {
  const result = await request<{ conversations: CopilotConversation[] }>("conversations");
  return result.conversations;
}

export function getCopilotConversation(id: string): Promise<{ conversation_id: string; messages: CopilotMessage[] }> {
  return request(`conversations/${encodeURIComponent(id)}`);
}

export function askCopilot(query: string, conversationId?: string): Promise<CopilotResponse> {
  return request("query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      ...(conversationId ? { conversation_id: conversationId } : {}),
    }),
  });
}

export function deleteCopilotConversation(id: string): Promise<void> {
  return request(`conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
}
