"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  FileSearch,
  LoaderCircle,
  MessageSquareText,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  askCopilot,
  CopilotApiError,
  deleteCopilotConversation,
  getCopilotConversation,
  listCopilotConversations,
  type CopilotBlock,
  type CopilotCitation,
  type CopilotConversation,
  type CopilotMessage,
  type CopilotResponse,
} from "@/lib/copilot-api";
import { subscribeToAccessToken } from "@/lib/session-auth";

const suggestedQuestions = [
  "What are the most important announcements in my portfolio?",
  "How has revenue changed over the last four quarters for Reliance Industries?",
  "Who in my network has relevant banking experience?",
  "I am researching Reliance Industries. What happened and who can provide context?",
];

function friendlyError(error: unknown): string {
  return error instanceof CopilotApiError
    ? error.message
    : "The Copilot request could not be completed. Please try again.";
}

function layerLabel(layer: CopilotBlock["layer"]): string {
  return layer === "push" ? "Push" : layer === "pull" ? "Pull" : "Network";
}

function moduleHref(block: CopilotBlock): string {
  const ticker = typeof block.data.ticker === "string" ? block.data.ticker : "";
  if (block.layer === "push") return "/push";
  if (block.layer === "network") return "/network";
  return ticker ? `/research?ticker=${encodeURIComponent(ticker)}` : "/research";
}

function Citation({ citation }: { citation: CopilotCitation }) {
  return (
    <li className="rounded-md border border-line bg-surface-muted/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-ink">{citation.title}</span>
        {citation.ticker && <Badge variant="neutral">{citation.ticker}</Badge>}
        {citation.reporting_period && <span className="text-[11px] text-ink-muted">{citation.reporting_period}</span>}
        {citation.page_number !== null && <span className="text-[11px] text-ink-muted">p. {citation.page_number}</span>}
        {citation.is_synthetic && <Badge variant="caution">Synthetic demo</Badge>}
      </div>
      {citation.quote && <p className="mt-2 text-xs leading-5 text-ink-secondary">{citation.quote}</p>}
      {citation.source_url && (
        <a
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
          href={citation.source_url}
          target="_blank"
          rel="noreferrer"
        >
          Open source <ArrowUpRight aria-hidden="true" size={13} />
        </a>
      )}
    </li>
  );
}

function AnswerBlock({ block }: { block: CopilotBlock }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge variant={block.layer === "pull" ? "info" : block.layer === "network" ? "positive" : "brand"}>
            {layerLabel(block.layer)}
          </Badge>
          <h3 className="text-sm font-semibold text-ink">{block.heading}</h3>
        </div>
        <Link className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-brand" href={moduleHref(block)}>
          Open workspace <ArrowUpRight aria-hidden="true" size={13} />
        </Link>
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink-secondary">{block.summary}</p>
      {block.citations.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs font-semibold text-brand">
            Evidence and citations ({block.citations.length})
          </summary>
          <ul className="mt-3 grid gap-2">
            {block.citations.map((citation, index) => (
              <Citation key={`${citation.source_type}-${citation.title}-${index}`} citation={citation} />
            ))}
          </ul>
        </details>
      )}
      {block.citations.length === 0 && (
        <p className="mt-3 text-xs text-ink-muted">No source citation was returned for this section.</p>
      )}
    </section>
  );
}

function Result({ result }: { result: CopilotResponse }) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-brand/15 bg-brand-tint/60 p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="brand">{result.intent.replaceAll("_", " ")}</Badge>
          {result.layers.map((layer) => <Badge key={layer} variant="neutral">{layerLabel(layer)}</Badge>)}
        </div>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink">{result.answer}</p>
      </div>

      {result.blocks.map((block, index) => <AnswerBlock key={`${block.layer}-${index}`} block={block} />)}

      {result.tools.length > 0 && (
        <details className="rounded-lg border border-line bg-surface p-4">
          <summary className="cursor-pointer text-xs font-semibold text-ink">Service execution details</summary>
          <ul className="mt-3 space-y-2">
            {result.tools.map((tool) => (
              <li key={tool.name} className="flex flex-wrap items-center gap-2 text-xs">
                <Badge variant={tool.status === "complete" ? "positive" : tool.status === "partial" ? "caution" : "neutral"}>
                  {tool.status}
                </Badge>
                <span className="font-medium text-ink">{tool.name.replaceAll("_", " ")}</span>
                <span className="text-ink-secondary">{tool.message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {result.limitations.length > 0 && (
        <div className="rounded-md border border-caution/20 bg-caution-tint p-3">
          <p className="text-xs font-semibold text-caution">Coverage limitations</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-caution">
            {result.limitations.map((limitation, index) => <li key={`${index}-${limitation}`}>{limitation}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function HistoryMessage({ message }: { message: CopilotMessage }) {
  if (message.role === "user") {
    return (
      <div className="ml-auto max-w-[92%] rounded-lg border border-line bg-surface-muted p-3 sm:max-w-[80%]">
        <p className="whitespace-pre-wrap text-sm leading-6 text-ink">{message.content}</p>
      </div>
    );
  }
  if (message.result) return <Result result={message.result} />;
  return <p className="text-sm text-ink-secondary">{message.content}</p>;
}

export function CopilotWorkspace() {
  const [query, setQuery] = useState("");
  const [conversations, setConversations] = useState<CopilotConversation[]>([]);
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [activeConversation, setActiveConversation] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      setConversations(await listCopilotConversations());
    } catch (reason) {
      setHistoryError(friendlyError(reason));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(refreshHistory);
    return subscribeToAccessToken(() => void refreshHistory());
  }, [refreshHistory]);

  const loadConversation = async (id: string) => {
    setHistoryLoading(true);
    setHistoryError("");
    setError("");
    try {
      const history = await getCopilotConversation(id);
      setMessages(history.messages);
      setActiveConversation(id);
    } catch (reason) {
      setHistoryError(friendlyError(reason));
    } finally {
      setHistoryLoading(false);
    }
  };

  const startNew = () => {
    setActiveConversation(undefined);
    setMessages([]);
    setError("");
    setQuery("");
  };

  const submit = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    const cleanQuery = query.trim();
    if (cleanQuery.length < 3 || loading) return;
    setLoading(true);
    setError("");
    const optimistic: CopilotMessage[] = [
      ...messages,
      {
        id: `pending-${Date.now()}`,
        role: "user",
        content: cleanQuery,
        result: null,
        created_at: new Date().toISOString(),
      },
    ];
    setMessages(optimistic);
    setQuery("");
    try {
      const response = await askCopilot(cleanQuery, activeConversation);
      const nextMessages = optimistic.filter((message) => !message.id.startsWith("pending-"));
      setMessages([
        ...nextMessages,
        {
          id: `user-${response.message_id}`,
          role: "user",
          content: cleanQuery,
          result: null,
          created_at: response.created_at,
        },
        {
          id: response.message_id,
          role: "assistant",
          content: response.answer,
          result: response,
          created_at: response.created_at,
        },
      ]);
      setActiveConversation(response.conversation_id);
      await refreshHistory();
    } catch (reason) {
      setMessages(optimistic.filter((message) => !message.id.startsWith("pending-")));
      setQuery(cleanQuery);
      setError(friendlyError(reason));
    } finally {
      setLoading(false);
    }
  };

  const removeConversation = async (conversation: CopilotConversation) => {
    if (!window.confirm("Delete this saved Copilot conversation?")) return;
    setHistoryError("");
    try {
      await deleteCopilotConversation(conversation.id);
      setConversations((items) => items.filter((item) => item.id !== conversation.id));
      if (activeConversation === conversation.id) startNew();
    } catch (reason) {
      setHistoryError(friendlyError(reason));
    }
  };

  const selectSuggestion = (question: string) => setQuery(question);

  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <header className="mb-6 border-b border-line pb-5">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted">Integrated intelligence · Push / Pull / Network</p>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[26px] font-semibold tracking-[-0.04em] text-ink">Research copilot</h1>
          <Badge variant="brand">Evidence-first</Badge>
        </div>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-ink-secondary">
          Ask across portfolio developments, primary-source company research, and your recorded professional network. Financial calculations and relationship retrieval stay deterministic.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[270px_minmax(0,1fr)]">
        <aside className="order-2 space-y-3 lg:order-1">
          <Button className="w-full justify-start" onClick={startNew}>
            <Plus aria-hidden="true" size={16} /> New research question
          </Button>
          <div className="rounded-lg border border-line bg-surface">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <h2 className="text-xs font-semibold text-ink">Private history</h2>
              <MessageSquareText aria-hidden="true" className="text-ink-muted" size={15} />
            </div>
            {historyError && <p role="alert" className="m-3 rounded bg-negative-tint p-2 text-xs text-negative">{historyError}</p>}
            <div className="max-h-[360px] space-y-1 overflow-y-auto p-2">
              {historyLoading && conversations.length === 0 && (
                <div className="space-y-2 p-2" aria-label="Loading conversation history">
                  <div className="h-10 animate-pulse rounded bg-surface-muted" />
                  <div className="h-10 animate-pulse rounded bg-surface-muted" />
                </div>
              )}
              {!historyLoading && conversations.length === 0 && (
                <p className="p-3 text-xs leading-5 text-ink-muted">Saved questions for this account will appear here.</p>
              )}
              {conversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={`group flex items-start gap-1 rounded-md p-2 ${activeConversation === conversation.id ? "bg-brand-tint" : "hover:bg-surface-muted"}`}
                >
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => void loadConversation(conversation.id)}
                    type="button"
                  >
                    <span className="block truncate text-xs font-medium text-ink">{conversation.title}</span>
                    <span className="mt-1 block truncate text-[11px] text-ink-muted">{conversation.last_message_preview ?? "No messages"}</span>
                  </button>
                  <button
                    aria-label={`Delete conversation: ${conversation.title}`}
                    className="rounded p-1 text-ink-muted opacity-70 hover:bg-negative-tint hover:text-negative sm:opacity-0 sm:group-hover:opacity-100"
                    onClick={() => void removeConversation(conversation)}
                    type="button"
                  >
                    <Trash2 aria-hidden="true" size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-line bg-surface p-4">
            <div className="flex items-center gap-2">
              <FileSearch aria-hidden="true" className="text-brand" size={16} />
              <h2 className="text-xs font-semibold text-ink">Evidence boundaries</h2>
            </div>
            <p className="mt-2 text-xs leading-5 text-ink-secondary">Company answers preserve primary-source citations. Network recommendations include only recorded relationship evidence; synthetic records are labelled.</p>
          </div>
        </aside>

        <main className="order-1 min-w-0 space-y-4 lg:order-2">
          {messages.length > 0 ? (
            <div className="space-y-4" aria-live="polite">
              {messages.map((message) => <HistoryMessage key={message.id} message={message} />)}
            </div>
          ) : (
            <section className="rounded-lg border border-line bg-surface p-5 sm:p-7">
              <div className="flex items-start gap-3">
                <span className="rounded-md bg-brand-tint p-2 text-brand"><Sparkles aria-hidden="true" size={18} /></span>
                <div>
                  <h2 className="text-sm font-semibold text-ink">Start with an investment question</h2>
                  <p className="mt-1 max-w-2xl text-xs leading-5 text-ink-secondary">FINN routes each question to the relevant backend services. Unsupported or missing evidence is shown explicitly rather than filled from model memory.</p>
                </div>
              </div>
              <div className="mt-5 grid gap-2 sm:grid-cols-2">
                {suggestedQuestions.map((question) => (
                  <button
                    key={question}
                    className="min-h-12 rounded-md border border-line px-3 py-2 text-left text-xs leading-5 text-ink-secondary hover:border-brand/40 hover:bg-brand-tint/40 hover:text-ink"
                    onClick={() => selectSuggestion(question)}
                    type="button"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </section>
          )}

          {error && <div role="alert" className="rounded-md border border-negative/20 bg-negative-tint p-3 text-sm text-negative">{error}</div>}

          <form onSubmit={(event) => void submit(event)} className="sticky bottom-2 rounded-lg border border-line bg-surface p-3 shadow-sm sm:p-4">
            <label className="sr-only" htmlFor="copilot-query">Ask FINN a research question</label>
            <textarea
              id="copilot-query"
              className="min-h-24 w-full resize-y rounded-md border border-line bg-surface px-3 py-3 text-sm leading-6 text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none"
              maxLength={2000}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask about portfolio announcements, company financials, guidance, or relevant network context…"
              value={query}
            />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] text-ink-muted">{query.length}/2000 · Company-specific questions need an NSE ticker or unambiguous company name.</span>
              <Button disabled={loading || query.trim().length < 3} type="submit">
                {loading ? <LoaderCircle aria-hidden="true" className="animate-spin" size={16} /> : <Sparkles aria-hidden="true" size={16} />}
                {loading ? "Researching…" : "Ask FINN"}
              </Button>
            </div>
          </form>

          {loading && (
            <div className="space-y-3" aria-label="Research in progress">
              <div className="h-24 animate-pulse rounded-lg border border-line bg-surface-muted" />
              <div className="h-36 animate-pulse rounded-lg border border-line bg-surface-muted" />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
