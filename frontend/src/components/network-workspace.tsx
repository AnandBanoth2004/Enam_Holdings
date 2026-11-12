"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import {
  AlertCircle,
  ArrowDownUp,
  BriefcaseBusiness,
  Building2,
  Check,
  ChevronRight,
  GraduationCap,
  Link2,
  LoaderCircle,
  LockKeyhole,
  Network,
  Search,
  ShieldCheck,
  UserRound,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  fetchCompanyConnections,
  fetchNetworkRecommendations,
  fetchRelationshipPath,
  searchNetworkContacts,
  searchNetworkExpertise,
  type NetworkContact,
  type NetworkPathStep,
  type NetworkRecommendation,
} from "@/lib/network-api";
import { searchCompanies } from "@/lib/research-api";
import {
  getAccessToken,
  setAccessToken,
  subscribeToAccessToken,
} from "@/lib/session-auth";
import { cn } from "@/lib/utils";

type SearchMode = "people" | "company" | "expertise";
type DegreeFilter = "all" | "1" | "2";
type RecommendationWorkflow =
  | "who_to_call"
  | "second_degree_reach"
  | "management_diligence"
  | "sector_expertise"
  | "keep_warm";

const MOBILE_NETWORK_QUERY = "(max-width: 639px)";

function subscribeToNetworkViewport(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const media = window.matchMedia(MOBILE_NETWORK_QUERY);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}

type RelationshipNodeData = {
  label: string;
  role: string;
  degree: "investor" | 1 | 2;
  synthetic: boolean;
  selected: boolean;
};

function RelationshipNode({ data }: NodeProps<Node<RelationshipNodeData>>) {
  const isInvestor = data.degree === "investor";
  return (
    <div
      className={cn(
        "w-[154px] rounded-lg border px-3 py-2.5 shadow-sm transition-colors",
        isInvestor
          ? "border-brand bg-brand text-white"
          : data.selected
            ? "border-info bg-info-tint ring-2 ring-info/30"
            : data.degree === 1
              ? "border-line bg-white hover:border-brand/50"
              : "border-dashed border-line bg-surface-muted hover:border-brand/50",
      )}
    >
      <Handle position={Position.Left} type="target" />
      <div className="flex items-start gap-2">
        <span
          className={cn(
            "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full",
            isInvestor ? "bg-white/15" : "bg-brand-tint text-brand",
          )}
        >
          {isInvestor ? <UserRound size={14} /> : <BriefcaseBusiness size={14} />}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[11px] font-semibold">{data.label}</span>
          <span
            className={cn(
              "mt-0.5 block truncate text-[9px]",
              isInvestor ? "text-white/70" : "text-ink-muted",
            )}
          >
            {isInvestor ? "Workspace investor" : data.role}
          </span>
        </span>
      </div>
      {!isInvestor ? (
        <div className="mt-2 flex items-center justify-between border-t border-line/70 pt-1.5">
          <span className="text-[9px] font-medium text-ink-secondary">
            {data.degree === 1 ? "1st degree" : "2nd degree"}
          </span>
          {data.synthetic ? (
            <span className="text-[8px] font-semibold uppercase tracking-wide text-caution">
              Fictional
            </span>
          ) : null}
        </div>
      ) : null}
      <Handle position={Position.Right} type="source" />
    </div>
  );
}

const nodeTypes = { relationship: RelationshipNode };

function toGraph(
  contacts: NetworkContact[],
  degree: DegreeFilter,
  selectedId: string | null,
  highlightedPath: NetworkPathStep[],
  mobile: boolean,
): { nodes: Node<RelationshipNodeData>[]; edges: Edge[] } {
  const reachable = contacts.filter((contact) => contact.connection_distance !== null);
  const targets = reachable
    .filter((contact) => degree === "all" || contact.connection_distance === Number(degree))
    .slice(0, 18);
  const targetIds = new Set(targets.map((contact) => contact.id));
  const bridgeIds = new Set(
    targets.flatMap((contact) =>
      contact.relationship_path
        .filter((step) => step.contact_id !== contact.id)
        .map((step) => step.contact_id),
    ),
  );
  const degreeOne = reachable.filter((contact) =>
    contact.connection_distance === 1 && (targetIds.has(contact.id) || bridgeIds.has(contact.id)),
  );
  const degreeTwo = targets.filter((contact) => contact.connection_distance === 2);
  const visibleContacts = [...new Map([...degreeOne, ...degreeTwo].map((item) => [item.id, item])).values()];
  const visibleIds = new Set(visibleContacts.map((contact) => contact.id));
  const missingBridgeSteps = targets.flatMap((contact) =>
    contact.relationship_path.filter(
      (step) => step.contact_id !== contact.id && !visibleIds.has(step.contact_id),
    ),
  );
  for (const step of missingBridgeSteps) visibleIds.add(step.contact_id);
  const nodes: Node<RelationshipNodeData>[] = [
    {
      id: "investor",
      type: "relationship",
      position: mobile ? { x: 105, y: 10 } : { x: 30, y: 210 },
      data: {
        label: "You",
        role: "Workspace investor",
        degree: "investor",
        synthetic: false,
        selected: false,
      },
      selectable: false,
    },
    ...degreeOne.map((contact, index) => ({
      id: contact.id,
      type: "relationship",
      position: mobile
        ? { x: 5, y: 145 + index * 90 }
        : { x: 300, y: 35 + index * 100 },
      data: {
        label: contact.display_name,
        role: contact.current_role ?? contact.current_employer ?? "Professional profile",
        degree: 1 as const,
        synthetic: contact.is_synthetic,
        selected: selectedId === contact.id,
      },
    })),
    ...degreeTwo.map((contact, index) => ({
      id: contact.id,
      type: "relationship",
      position: mobile
        ? { x: 200, y: 145 + index * 90 }
        : { x: 575, y: 70 + index * 110 },
      data: {
        label: contact.display_name,
        role: contact.current_role ?? contact.current_employer ?? "Professional profile",
        degree: 2 as const,
        synthetic: contact.is_synthetic,
        selected: selectedId === contact.id,
      },
    })),
    ...[...new Map(missingBridgeSteps.map((step) => [step.contact_id, step])).values()].map((step, index) => ({
      id: step.contact_id,
      type: "relationship",
      position: mobile
        ? { x: 5, y: 145 + (degreeOne.length + index) * 90 }
        : { x: 300, y: 35 + (degreeOne.length + index) * 100 },
      data: {
        label: step.name,
        role: "Recorded relationship path",
        degree: 1 as const,
        synthetic: false,
        selected: false,
      },
      selectable: false,
    })),
  ];
  const edgesById = new Map<string, Edge>();
  const selectedIds = new Set(highlightedPath.map((step) => step.contact_id));
  for (const contact of targets) {
    let sourceId = "investor";
    for (const step of contact.relationship_path) {
      if (!visibleIds.has(step.contact_id)) continue;
      const id = `${sourceId}-${step.contact_id}`;
      const highlighted =
        selectedId === contact.id &&
        (selectedIds.has(step.contact_id) || step.contact_id === contact.id);
      edgesById.set(id, {
        id,
        source: sourceId,
        target: step.contact_id,
        label: step.relationship_type.replaceAll("_", " "),
        animated: highlighted,
        style: {
          stroke: highlighted ? "#356a8a" : "#b9c5ce",
          strokeWidth: highlighted ? 2.5 : 1.4,
        },
        labelStyle: { fill: "#526171", fontSize: 9 },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.9 },
      });
      sourceId = step.contact_id;
    }
  }
  return { nodes, edges: [...edgesById.values()] };
}

function overlappingLabels(selected: NetworkContact, contacts: NetworkContact[]) {
  const names = new Map<string, { employers: Set<string>; education: Set<string> }>();
  for (const contact of contacts) {
    if (contact.id === selected.id) continue;
    const employers = new Set(
      contact.previous_employers.map((item) => item.trim().toLocaleLowerCase()),
    );
    const education = new Set(
      contact.education.map((item) => item.institution.trim().toLocaleLowerCase()),
    );
    names.set(contact.display_name, { employers, education });
  }
  const sharedEmployers = new Set(
    selected.previous_employers.map((item) => item.trim().toLocaleLowerCase()),
  );
  const sharedEducation = new Set(
    selected.education.map((item) => item.institution.trim().toLocaleLowerCase()),
  );
  const employerPeers: string[] = [];
  const educationPeers: string[] = [];
  for (const [name, groups] of names) {
    if ([...groups.employers].some((item) => sharedEmployers.has(item))) employerPeers.push(name);
    if ([...groups.education].some((item) => sharedEducation.has(item))) educationPeers.push(name);
  }
  return { employerPeers, educationPeers };
}

function ProfileDetails({
  contact,
  contacts,
  path,
  onClose,
}: {
  contact: NetworkContact;
  contacts: NetworkContact[];
  path: { distance: 1 | 2 | null; path: NetworkPathStep[]; explanation: string } | null;
  onClose: () => void;
}) {
  const overlaps = overlappingLabels(contact, contacts);
  return (
    <aside
      aria-label={`${contact.display_name} profile`}
      className="rounded-lg border border-line bg-surface p-4 sm:p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-ink">{contact.display_name}</h2>
            {contact.is_synthetic ? <Badge variant="caution">Fictional demo</Badge> : null}
          </div>
          <p className="mt-1 text-xs text-ink-secondary">
            {contact.current_role ?? "Role unavailable"}
            {contact.current_employer ? ` · ${contact.current_employer}` : ""}
          </p>
        </div>
        <Button aria-label="Close profile" onClick={onClose} size="icon" variant="ghost">
          <X size={15} />
        </Button>
      </div>

      <div className="mt-4 rounded-md bg-brand-tint/60 p-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-brand">
          <Link2 size={14} />
          {path?.distance === 1 ? "First-degree relationship" : path?.distance === 2 ? "Second-degree reach" : "No recorded relationship"}
        </div>
        <p className="mt-1 text-[11px] leading-5 text-ink-secondary">
          {path?.explanation ?? "Relationship path is being loaded."}
        </p>
        {path?.path.length ? (
          <ol className="mt-2 space-y-2">
            {path.path.map((step, index) => (
              <li className="flex items-start gap-2 text-[10px] leading-4 text-ink-secondary" key={`${step.contact_id}-${index}`}>
                <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-white text-[9px] font-semibold text-brand">
                  {index + 1}
                </span>
                <span>
                  <strong className="font-semibold text-ink">{step.name}</strong>
                  {` · ${step.relationship_type.replaceAll("_", " ")}`}
                  {step.evidence ? <span className="mt-0.5 block">{step.evidence}</span> : null}
                </span>
              </li>
            ))}
          </ol>
        ) : null}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <ProfileList
          icon={<BriefcaseBusiness size={13} />}
          items={[
            ...(contact.current_employer ? [`Current · ${contact.current_employer}`] : []),
            ...contact.previous_employers.map((employer) => `Previous · ${employer}`),
          ]}
          title="Employment history"
        />
        <ProfileList
          icon={<GraduationCap size={13} />}
          items={contact.education.map(
            (item) =>
              `${item.institution}${item.graduation_year ? ` · ${item.graduation_year}` : ""}${item.qualification ? ` · ${item.qualification}` : ""}`,
          )}
          title="Education"
        />
        <ProfileList
          icon={<Building2 size={13} />}
          items={contact.industry_experience}
          title="Industry experience"
        />
        <ProfileList
          icon={<ArrowDownUp size={13} />}
          items={contact.expertise}
          title="Expertise from recorded roles"
        />
        <ProfileList
          icon={<Building2 size={13} />}
          items={contact.companies_worked_with}
          title="Companies worked with"
        />
      </div>
      <div className="mt-4 grid gap-2 rounded-md border border-line bg-white p-3 sm:grid-cols-2">
        <div>
          <p className="text-[9px] font-semibold uppercase tracking-wide text-ink-muted">Relationship strength</p>
          <p className="mt-1 text-[11px] text-ink-secondary">{contact.relationship_strength ?? "Not recorded"}</p>
        </div>
        <div>
          <p className="text-[9px] font-semibold uppercase tracking-wide text-ink-muted">Last interaction</p>
          <p className="mt-1 text-[11px] text-ink-secondary">
            {contact.last_interaction
              ? new Date(contact.last_interaction).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })
              : "Not recorded"}
          </p>
        </div>
        {contact.relationship_evidence ? (
          <p className="text-[10px] leading-4 text-ink-secondary sm:col-span-2">
            <strong className="font-semibold text-ink">Relationship evidence: </strong>
            {contact.relationship_evidence}
          </p>
        ) : null}
      </div>

      <div className="mt-4 grid gap-3 border-t border-line pt-3 sm:grid-cols-2">
        <OverlapList title="Previous-employer overlap" names={overlaps.employerPeers} />
        <OverlapList title="Education overlap" names={overlaps.educationPeers} />
      </div>
      <p className="mt-3 text-[10px] leading-4 text-ink-muted">
        Employer and education overlap describe shared background only; they do not prove that these contacts know each other.
      </p>
    </aside>
  );
}

function ProfileList({
  icon,
  title,
  items,
}: {
  icon: ReactNode;
  title: string;
  items: string[];
}) {
  return (
    <div className="min-w-0">
      <h3 className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
        {icon}
        {title}
      </h3>
      {items.length ? (
        <ul className="mt-2 space-y-1.5">
          {items.map((item) => (
            <li className="text-[11px] leading-4 text-ink-secondary" key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[11px] text-ink-muted">Not available in the profile.</p>
      )}
    </div>
  );
}

function OverlapList({ title, names }: { title: string; names: string[] }) {
  return (
    <div>
      <h3 className="text-[10px] font-semibold uppercase tracking-wide text-ink-muted">{title}</h3>
      {names.length ? (
        <p className="mt-1 text-[11px] leading-4 text-ink-secondary">{names.join(", ")}</p>
      ) : (
        <p className="mt-1 text-[11px] text-ink-muted">No shared records found.</p>
      )}
    </div>
  );
}

function ConnectToken({ onTokenChange }: { onTokenChange: () => void }) {
  const [token, setToken] = useState("");
  const [open, setOpen] = useState(false);
  const connected = useSyncExternalStore(
    subscribeToAccessToken,
    () => Boolean(getAccessToken()),
    () => false,
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAccessToken(token);
    setToken("");
    setOpen(false);
    onTokenChange();
  }

  return (
    <div className="relative">
      <Button
        onClick={() => setOpen((value) => !value)}
        size="sm"
        type="button"
        variant={connected ? "outline" : "primary"}
      >
        {connected ? <ShieldCheck size={14} /> : <LockKeyhole size={14} />}
        {connected ? "Workspace connected" : "Connect workspace"}
      </Button>
      {open ? (
        <form
          className="absolute right-0 top-full z-30 mt-2 w-[min(90vw,360px)] rounded-lg border border-line bg-white p-4 shadow-xl"
          onSubmit={submit}
        >
          <label className="block text-xs font-semibold text-ink" htmlFor="network-access-token">
            Supabase access token
          </label>
          <p className="mt-1 text-[11px] leading-4 text-ink-secondary">
            Used only for this browser tab session and sent to the FINN API for JWT verification. Do not enter a service-role key.
          </p>
          <input
            autoComplete="off"
            className="mt-3 min-h-10 w-full rounded-md border border-line px-3 text-xs outline-none focus:border-info"
            id="network-access-token"
            onChange={(event) => setToken(event.target.value)}
            placeholder={connected ? "Enter a replacement token" : "Paste a user access token"}
            type="password"
            value={token}
          />
          <div className="mt-3 flex justify-between gap-2">
            {connected ? (
              <Button
                onClick={() => {
                  setAccessToken("");
                  setOpen(false);
                  onTokenChange();
                }}
                size="sm"
                type="button"
                variant="ghost"
              >
                Disconnect
              </Button>
            ) : <span />}
            <Button disabled={!token.trim()} size="sm" type="submit">Save for this session</Button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

export function NetworkRecommendationsPanel({
  ticker,
  workflow = "who_to_call",
  title = "Network context",
  executive,
  compact = false,
}: {
  ticker: string;
  workflow?: RecommendationWorkflow;
  title?: string;
  executive?: string;
  compact?: boolean;
}) {
  const [recommendations, setRecommendations] = useState<NetworkRecommendation[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void fetchNetworkRecommendations({ workflow, ticker, executive, limit: 3 })
      .then((result) => {
        if (!active) return;
        setError("");
        setRecommendations(result.recommendations);
        setNotice(result.notice);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setRecommendations([]);
        setError(cause instanceof Error ? cause.message : "Network context is unavailable.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [executive, ticker, workflow]);

  return (
    <section className={cn("rounded-lg border border-line bg-surface", compact ? "p-3 sm:p-4" : "p-4 sm:p-5")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
            Network · {workflow.replaceAll("_", " ")}
          </p>
          <h2 className="mt-1 text-sm font-semibold text-ink">{title}</h2>
        </div>
        <Link className="inline-flex min-h-9 items-center gap-1 text-[11px] font-medium text-brand hover:underline" href="/network">
          Open network
          <ChevronRight size={13} />
        </Link>
      </div>
      {loading ? (
        <div className="mt-3 flex items-center gap-2 text-xs text-ink-muted" role="status">
          <LoaderCircle className="animate-spin" size={14} />
          Loading workspace connections…
        </div>
      ) : error ? (
        <div className="mt-3 rounded-md bg-caution-tint/70 p-3 text-[11px] leading-5 text-ink-secondary" role="status">
          <p className="flex items-center gap-1.5 font-semibold text-caution"><AlertCircle size={13} /> Network context not available</p>
          <p className="mt-1">{error}</p>
          <p className="mt-1">Connect an authorized user token in Network intelligence to view private workspace contacts.</p>
        </div>
      ) : recommendations.length ? (
        <div className={cn("mt-3 grid gap-2", compact ? "" : "sm:grid-cols-2 xl:grid-cols-3")}>
          {recommendations.map((item) => (
            <article className="min-w-0 rounded-md border border-line bg-white p-3" key={item.contact.id}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-xs font-semibold text-ink">{item.contact.display_name}</p>
                  <p className="mt-0.5 line-clamp-2 text-[10px] text-ink-secondary">
                    {item.contact.current_role ?? "Role unavailable"}
                    {item.contact.current_employer ? ` · ${item.contact.current_employer}` : ""}
                  </p>
                </div>
                <Badge variant="info">{item.connection_distance === 1 ? "1st" : "2nd"} degree</Badge>
              </div>
              <p className="mt-2 line-clamp-3 text-[10px] leading-4 text-ink-secondary">
                {item.reasons.find((reason) => reason.includes("Experience") || reason.includes("Profile")) ??
                  item.reasons.find((reason) => reason.includes("evidence")) ??
                  item.reasons[0] ??
                  "The API returned no recommendation rationale."}
              </p>
              <p className="mt-1 line-clamp-1 text-[9px] text-ink-muted">
                Path: You {"→"} {item.path.map((step) => step.name).join(" → ") || "unavailable"}
              </p>
              <div className="mt-2 flex items-center gap-2">
                {item.contact.is_synthetic ? <Badge variant="caution">Fictional demo</Badge> : null}
                <span className="text-[9px] text-ink-muted">Relevance {item.score}/100</span>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="mt-3 rounded-md bg-surface-muted p-3 text-[11px] leading-5 text-ink-secondary">
          No reachable contacts with matching company experience were returned. FINN does not infer a relationship from employer overlap.
        </p>
      )}
      {!loading && notice ? <p className="mt-2 text-[9px] leading-4 text-ink-muted">{notice}</p> : null}
    </section>
  );
}

export function NetworkWorkspace() {
  const mobile = useSyncExternalStore(
    subscribeToNetworkViewport,
    () => window.matchMedia(MOBILE_NETWORK_QUERY).matches,
    () => false,
  );
  const [mode, setMode] = useState<SearchMode>("people");
  const [degree, setDegree] = useState<DegreeFilter>("all");
  const [query, setQuery] = useState("");
  const [contacts, setContacts] = useState<NetworkContact[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<{
    distance: 1 | 2 | null;
    path: NetworkPathStep[];
    explanation: string;
  } | null>(null);
  const [recommendations, setRecommendations] = useState<NetworkRecommendation[]>([]);
  const [workflow, setWorkflow] = useState<RecommendationWorkflow>("who_to_call");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sourceLabel, setSourceLabel] = useState("Workspace relationships");
  const [notice, setNotice] = useState("");

  const selected = contacts.find((contact) => contact.id === selectedId) ?? null;
  const filteredContacts = useMemo(
    () => contacts.filter((contact) => degree === "all" || contact.connection_distance === Number(degree)),
    [contacts, degree],
  );
  const graph = useMemo(
    () => toGraph(contacts, degree, selectedId, selectedPath?.path ?? [], mobile),
    [contacts, degree, mobile, selectedId, selectedPath],
  );

  const loadContacts = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await searchNetworkContacts();
      setContacts(result.contacts);
      setSourceLabel("Workspace relationships");
      setNotice("");
      setSelectedId((previous) =>
        previous && result.contacts.some((contact) => contact.id === previous) ? previous : null,
      );
    } catch (cause) {
      setContacts([]);
      setError(cause instanceof Error ? cause.message : "Network contacts could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void searchNetworkContacts()
      .then((result) => {
        if (!active) return;
        setContacts(result.contacts);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setContacts([]);
        setError(cause instanceof Error ? cause.message : "Network contacts could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    let active = true;
    void fetchRelationshipPath(selectedId)
      .then((result) => {
        if (active) setSelectedPath(result);
      })
      .catch((cause: unknown) => {
        if (active) setSelectedPath({
          distance: null,
          path: [],
          explanation: cause instanceof Error ? cause.message : "Could not load the relationship path.",
        });
      });
    return () => {
      active = false;
    };
  }, [selectedId]);

  const runSearch = useCallback(async () => {
    const search = query.trim();
    setBusy(true);
    setError("");
    setRecommendations([]);
    try {
      if (mode === "company") {
        const normalizedTicker = search.toUpperCase().replace(/\.NS$/, "");
        const tickerLike = /^[A-Z0-9&-]{1,20}$/.test(normalizedTicker);
        let ticker = normalizedTicker;
        if (!tickerLike) {
          const matches = (await searchCompanies(search)).results.filter(
            (item) => item.exchange === "NSE",
          );
          const exact = matches.find(
            (item) =>
              item.company_name.trim().toLocaleLowerCase() === search.toLocaleLowerCase() ||
              item.ticker.toLocaleLowerCase() === normalizedTicker.toLocaleLowerCase(),
          );
          const unique = matches.length === 1 ? matches[0] : undefined;
          const match = exact ?? unique;
          if (!match) {
            throw new Error(
              "Could not resolve this name to one NSE-listed company. Refine the name or search by ticker.",
            );
          }
          ticker = match.ticker;
        }
        const result = await fetchCompanyConnections(ticker);
        setContacts(result.contacts);
        setSourceLabel(`${result.ticker} · ${result.company_name}`);
        setNotice(result.match_evidence.join(" "));
      } else if (mode === "expertise") {
        const result = await searchNetworkExpertise(search);
        setContacts(result.contacts);
        setSourceLabel(`Expertise · ${search}`);
        setNotice("Matches are based on recorded role, sector, and employer history, not inferred expertise.");
      } else {
        const result = await searchNetworkContacts(search);
        setContacts(result.contacts);
        setSourceLabel(search ? `People · ${search}` : "Workspace relationships");
        setNotice("");
      }
      setSelectedId(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Search could not be completed.");
    } finally {
      setBusy(false);
    }
  }, [mode, query]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runSearch();
  }

  async function loadRecommendations() {
    setBusy(true);
    setError("");
    try {
      const result = await fetchNetworkRecommendations({
        workflow,
        ticker: mode === "company" ? query.trim() : undefined,
        expertise: mode === "expertise" ? query.trim() : undefined,
        limit: 12,
      });
      setRecommendations(result.recommendations);
      setContacts(result.recommendations.map((item) => item.contact));
      setSourceLabel(`Recommendations · ${workflow.replaceAll("_", " ")}`);
      setNotice(result.notice);
      setSelectedId(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Recommendations could not be loaded.");
    } finally {
      setBusy(false);
    }
  }

  const handleNodeClick = useCallback((_event: unknown, node: Node) => {
    if (node.id !== "investor") setSelectedId(node.id);
  }, []);

  const recommendationByContact = new Map(
    recommendations.map((item) => [item.contact.id, item]),
  );

  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4 border-b border-line pb-5">
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-ink-muted">Network · Relationship intelligence</p>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[26px] font-semibold tracking-[-0.04em] text-ink sm:text-[30px]">Network intelligence</h1>
            <Badge variant="caution">Fictional demo profiles</Badge>
          </div>
          <p className="mt-1 max-w-2xl text-sm leading-5 text-ink-secondary">
            Find relevant experience and warm paths with evidence. Shared career history is context, not proof of a relationship.
          </p>
        </div>
        <ConnectToken onTokenChange={() => void loadContacts()} />
      </div>

      <section className="mb-4 rounded-lg border border-line bg-surface p-3 sm:p-4">
        <form className="grid gap-3 lg:grid-cols-[145px_minmax(0,1fr)_auto]" onSubmit={submitSearch}>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
            Search by
            <select
              aria-label="Search mode"
              className="mt-1 h-10 w-full rounded-md border border-line bg-white px-2 text-xs font-medium text-ink"
              onChange={(event) => setMode(event.target.value as SearchMode)}
              value={mode}
            >
              <option value="people">People / profiles</option>
              <option value="company">Company / NSE ticker</option>
              <option value="expertise">Expertise / sector</option>
            </select>
          </label>
          <label className="min-w-0 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
            {mode === "company" ? "NSE company name or ticker" : mode === "expertise" ? "Role, expertise, or sector" : "Contact, employer, or role"}
            <span className="mt-1 flex min-h-10 items-center gap-2 rounded-md border border-line bg-white px-3 focus-within:ring-2 focus-within:ring-info">
              <Search className="shrink-0 text-ink-muted" size={15} />
              <input
                aria-label={mode === "company" ? "Company or ticker search" : "Contact or expertise search"}
                className="min-w-0 flex-1 bg-transparent text-xs font-normal text-ink outline-none placeholder:text-ink-muted"
                onChange={(event) => setQuery(event.target.value)}
                placeholder={mode === "company" ? "e.g. Reliance Industries or RELIANCE" : mode === "expertise" ? "e.g. credit risk" : "e.g. Mira Deshpande"}
                value={query}
              />
              {query ? (
                <button aria-label="Clear search" className="rounded p-1 text-ink-muted hover:bg-surface-muted" onClick={() => setQuery("")} type="button">
                  <X size={13} />
                </button>
              ) : null}
            </span>
          </label>
          <div className="flex items-end">
            <Button className="w-full lg:w-auto" disabled={busy || (mode !== "people" && !query.trim())} type="submit">
              {busy ? <LoaderCircle className="animate-spin" size={14} /> : <Search size={14} />}
              Search
            </Button>
          </div>
        </form>
        <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-line pt-3">
          <label className="text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
            Connection distance
            <select
              aria-label="Filter by connection distance"
              className="mt-1 block h-9 min-w-36 rounded-md border border-line bg-white px-2 text-xs font-medium text-ink"
              onChange={(event) => setDegree(event.target.value as DegreeFilter)}
              value={degree}
            >
              <option value="all">First + second degree</option>
              <option value="1">First degree</option>
              <option value="2">Second degree</option>
            </select>
          </label>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
            Recommended contacts
            <select
              aria-label="Recommendation workflow"
              className="mt-1 block h-9 min-w-48 rounded-md border border-line bg-white px-2 text-xs font-medium text-ink"
              onChange={(event) => setWorkflow(event.target.value as RecommendationWorkflow)}
              value={workflow}
            >
              <option value="who_to_call">Who should I call?</option>
              <option value="second_degree_reach">Second-degree reach</option>
              <option value="management_diligence">Management diligence</option>
              <option value="sector_expertise">Sector expertise</option>
              <option value="keep_warm">Keep the network warm</option>
            </select>
          </label>
          <Button disabled={busy} onClick={() => void loadRecommendations()} size="sm" type="button" variant="outline">
            {busy ? <LoaderCircle className="animate-spin" size={13} /> : <UsersRound size={13} />}
            Get recommendations
          </Button>
          <Button disabled={busy} onClick={() => void loadContacts()} size="sm" type="button" variant="ghost">
            Reset
          </Button>
        </div>
      </section>

      {error ? (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-caution/20 bg-caution-tint/50 p-3 text-xs leading-5 text-ink-secondary" role="alert">
          <AlertCircle className="mt-0.5 shrink-0 text-caution" size={15} />
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-ink">Network data unavailable</p>
            <p>{error}</p>
            <p className="mt-1">Private contact data requires a valid user access token and membership in the configured workspace. Connect it above; do not use a service-role key.</p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(330px,0.65fr)]">
        <section className="min-w-0 overflow-hidden rounded-lg border border-line bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-ink">Relationship map</h2>
              <p className="mt-0.5 truncate text-[10px] text-ink-muted">
                {sourceLabel} · {filteredContacts.filter((item) => item.connection_distance !== null).length} reachable profiles
              </p>
            </div>
            <span className="flex items-center gap-1.5 text-[10px] text-ink-muted">
              <span className="size-2 rounded-full bg-brand" /> Investor
              <span className="ml-1 size-2 rounded-full border border-line bg-white" /> 1st degree
              <span className="ml-1 size-2 rounded-full border border-dashed border-line bg-surface-muted" /> 2nd degree
            </span>
          </div>
          {loading ? (
            <div className="flex h-[390px] items-center justify-center gap-2 text-xs text-ink-muted" role="status">
              <LoaderCircle className="animate-spin" size={16} /> Loading workspace graph…
            </div>
          ) : graph.nodes.length > 1 ? (
            <div className="h-[390px] w-full sm:h-[470px]" data-testid="relationship-graph">
              <ReactFlow
                key={mobile ? "network-mobile" : "network-desktop"}
                edges={graph.edges}
                fitView
                fitViewOptions={{
                  padding: 0.1,
                  minZoom: mobile ? 0.35 : 0.7,
                  maxZoom: 1,
                }}
                minZoom={0.25}
                nodes={graph.nodes}
                nodeTypes={nodeTypes}
                onNodeClick={handleNodeClick}
                nodesConnectable={false}
                nodesDraggable={false}
                proOptions={{ hideAttribution: true }}
              >
                <Background color="#e2e8ed" gap={24} size={1} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          ) : (
            <div className="flex min-h-[300px] flex-col items-center justify-center px-6 text-center">
              <span className="flex size-10 items-center justify-center rounded-full bg-brand-tint text-brand"><Network size={18} /></span>
              <h3 className="mt-3 text-sm font-semibold text-ink">{error ? "Connect to load your network" : "No reachable connections found"}</h3>
              <p className="mt-1 max-w-sm text-xs leading-5 text-ink-secondary">
                {error ? "Authenticate with a user access token and confirm workspace membership." : "Try searching expertise or another NSE company. Career overlap alone is not shown as a relationship."}
              </p>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-2.5 text-[10px] text-ink-muted">
            <span className="inline-flex items-center gap-1.5"><ShieldCheck size={12} /> Only explicit relationship records are traversed</span>
            <span>Scroll to zoom · drag canvas to pan · select a node for details</span>
          </div>
        </section>

        <div className="min-w-0 space-y-4">
          {selected ? (
            <ProfileDetails
              contact={selected}
              contacts={contacts}
              onClose={() => setSelectedId(null)}
              path={selectedPath}
            />
          ) : (
            <div className="rounded-lg border border-dashed border-line bg-surface p-5 text-center sm:p-8">
              <span className="mx-auto flex size-10 items-center justify-center rounded-full bg-brand-tint text-brand"><UserRound size={17} /></span>
              <h2 className="mt-3 text-sm font-semibold text-ink">Select a contact</h2>
              <p className="mt-1 text-xs leading-5 text-ink-secondary">
                Choose a graph node or recommendation to inspect work history, education overlap, and the evidenced route.
              </p>
            </div>
          )}

          <section className="rounded-lg border border-line bg-surface p-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-muted">Evidence-ranked</p>
                <h2 className="mt-1 text-sm font-semibold text-ink">Recommended contacts</h2>
              </div>
              <Badge variant="info">{recommendations.length}</Badge>
            </div>
            {recommendations.length ? (
              <div className="mt-3 space-y-2">
                {recommendations.map((item) => (
                  <button
                    className={cn(
                      "w-full rounded-md border p-3 text-left transition-colors hover:border-brand/40 hover:bg-brand-tint/30",
                      selectedId === item.contact.id ? "border-info bg-info-tint/60" : "border-line bg-white",
                    )}
                    key={item.contact.id}
                    onClick={() => setSelectedId(item.contact.id)}
                    type="button"
                  >
                    <span className="flex items-start justify-between gap-2">
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-semibold text-ink">{item.contact.display_name}</span>
                        <span className="mt-0.5 block text-[10px] text-ink-secondary">{item.contact.current_role ?? "Role unavailable"}</span>
                      </span>
                      <span className="shrink-0 text-[10px] font-semibold text-brand">{item.score}/100</span>
                    </span>
                    <span className="mt-2 block text-[10px] leading-4 text-ink-secondary">{item.reasons[0]}</span>
                    <span className="mt-2 flex flex-wrap items-center gap-1.5">
                      <Badge variant={item.connection_distance === 1 ? "brand" : "neutral"}>
                        {item.connection_distance === 1 ? "First degree" : "Second degree"}
                      </Badge>
                      {item.contact.is_synthetic ? <Badge variant="caution">Fictional</Badge> : null}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="mt-3 rounded-md bg-surface-muted p-3 text-[11px] leading-5 text-ink-secondary">
                Select a workflow and choose <strong>Get recommendations</strong>. Each result will include its basis and path.
              </p>
            )}
            {notice ? <p className="mt-3 text-[10px] leading-4 text-ink-muted">{notice}</p> : null}
          </section>

          {selected && recommendationByContact.has(selected.id) ? (
            <div className="rounded-lg border border-line bg-surface p-4">
              <h3 className="text-xs font-semibold text-ink">Why this contact is relevant</h3>
              <ul className="mt-2 space-y-2">
                {recommendationByContact.get(selected.id)?.reasons.map((reason) => (
                  <li className="flex items-start gap-2 text-[10px] leading-4 text-ink-secondary" key={reason}>
                    <Check className="mt-0.5 shrink-0 text-positive" size={12} />
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>

      {!error ? (
        <div className="mt-4 flex flex-wrap items-start gap-2 rounded-lg border border-line bg-surface-muted/60 p-3 text-[10px] leading-4 text-ink-secondary">
          <LockKeyhole className="mt-0.5 shrink-0 text-brand" size={13} />
          <span>Contact records stay within the authorized workspace. Fictional demonstration identities and links are explicitly labeled. Similar employer or education history is never treated as proof of acquaintance.</span>
        </div>
      ) : null}
    </div>
  );
}
