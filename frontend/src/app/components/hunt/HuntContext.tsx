"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { useAuth } from "../auth/SessionProvider";

/* ══════════════════════════════════════════════
   Shared types (also re-exported for consumers)
   ══════════════════════════════════════════════ */

export interface ExtractedContext {
  industry: string | null;
  companyProfile: string | null;
  technologyFocus: string | null;
  qualifyingCriteria: string | null;
  disqualifiers: string | null;
  geographicRegion: string | null;
}

export interface SearchCompany {
  url: string;
  domain: string;
  title: string;
  snippet: string;
  score: number | null;
  source_query?: string;
}

export interface QualifiedCompany {
  title: string;
  domain: string;
  url: string;
  score: number;
  tier: "hot" | "review" | "rejected";
  hardware_type?: string | null;
  industry_category?: string | null;
  reasoning: string;
  key_signals: string[];
  red_flags: string[];
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface PipelineProgress {
  index: number;
  total: number;
  phase: "crawling" | "qualifying";
  company: string;
}

export interface PipelineSummary {
  hot: number;
  review: number;
  rejected: number;
  failed: number;
}

export interface EnrichedContact {
  domain: string;
  title: string;
  url: string;
  email: string | null;
  phone: string | null;
  job_title: string | null;
  source: string | null;
  found: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface Readiness {
  industry: boolean;
  companyProfile: boolean;
  technologyFocus: boolean;
  qualifyingCriteria: boolean;
  isReady: boolean;
}

export const INITIAL_READINESS: Readiness = {
  industry: false,
  companyProfile: false,
  technologyFocus: false,
  qualifyingCriteria: false,
  isReady: false,
};

export type Phase =
  | "chat"
  | "searching"
  | "search-complete"
  | "qualifying"
  | "complete";

/* ══════════════════════════════════════════════
   Context value shape
   ══════════════════════════════════════════════ */

interface HuntContextValue {
  /* ── Chat state (persists across navigation) ── */
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  readiness: Readiness;
  setReadiness: React.Dispatch<React.SetStateAction<Readiness>>;

  /* ── Pipeline state ── */
  phase: Phase;
  searchCompanies: SearchCompany[];
  allSearchCompanies: SearchCompany[];
  qualifiedCompanies: QualifiedCompany[];
  pipelineProgress: PipelineProgress | null;
  pipelineSummary: PipelineSummary | null;
  pipelineStartTime: number;
  extractedContext: ExtractedContext | null;
  enrichedContacts: Map<string, EnrichedContact>;
  enrichDone: boolean;

  /* ── Setters (exposed so ChatInterface can still drive them) ── */
  setPhase: (p: Phase) => void;
  setSearchCompanies: React.Dispatch<React.SetStateAction<SearchCompany[]>>;
  setAllSearchCompanies: React.Dispatch<React.SetStateAction<SearchCompany[]>>;
  setQualifiedCompanies: React.Dispatch<React.SetStateAction<QualifiedCompany[]>>;
  setPipelineProgress: React.Dispatch<React.SetStateAction<PipelineProgress | null>>;
  setPipelineSummary: React.Dispatch<React.SetStateAction<PipelineSummary | null>>;
  setPipelineStartTime: React.Dispatch<React.SetStateAction<number>>;
  setExtractedContext: React.Dispatch<React.SetStateAction<ExtractedContext | null>>;
  setEnrichedContacts: React.Dispatch<React.SetStateAction<Map<string, EnrichedContact>>>;
  setEnrichDone: React.Dispatch<React.SetStateAction<boolean>>;

  /* ── Actions ── */
  launchSearch: (ctx: ExtractedContext) => Promise<void>;
  launchPipeline: (batch: SearchCompany[], previousResults: QualifiedCompany[], ctx: ExtractedContext | null) => Promise<void>;
  resetHunt: () => void;
  /** Load a saved search (with messages + leads) back into context */
  resumeHunt: (searchId: string) => Promise<void>;

  /** The DB search ID (set after pipeline saves to DB) */
  searchId: string | null;

  /** True while an SSE pipeline stream is active */
  isPipelineRunning: boolean;
}

const HuntContext = createContext<HuntContextValue | null>(null);

export function useHunt() {
  const ctx = useContext(HuntContext);
  if (!ctx) throw new Error("useHunt must be used inside <HuntProvider>");
  return ctx;
}

/* ══════════════════════════════════════════════
   Provider — lives in root layout, survives navigation
   ══════════════════════════════════════════════ */

export function HuntProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();

  /* ── State ── */
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [readiness, setReadiness] = useState<Readiness>(INITIAL_READINESS);
  const [phase, setPhase] = useState<Phase>("chat");
  const [searchCompanies, setSearchCompanies] = useState<SearchCompany[]>([]);
  const [allSearchCompanies, setAllSearchCompanies] = useState<SearchCompany[]>([]);
  const [qualifiedCompanies, setQualifiedCompanies] = useState<QualifiedCompany[]>([]);
  const [pipelineProgress, setPipelineProgress] = useState<PipelineProgress | null>(null);
  const [pipelineSummary, setPipelineSummary] = useState<PipelineSummary | null>(null);
  const [pipelineStartTime, setPipelineStartTime] = useState<number>(0);
  const [extractedContext, setExtractedContext] = useState<ExtractedContext | null>(null);
  const [enrichedContacts, setEnrichedContacts] = useState<Map<string, EnrichedContact>>(new Map());
  const [enrichDone, setEnrichDone] = useState(false);
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);
  const [searchId, setSearchId] = useState<string | null>(null);

  // Abort controller for in-flight SSE so we can cancel on reset
  const abortRef = useRef<AbortController | null>(null);

  // Keep a ref to current messages so the pipeline closure can read them
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  /* ── Reset ── */
  const resetHunt = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setReadiness(INITIAL_READINESS);
    setPhase("chat");
    setSearchCompanies([]);
    setAllSearchCompanies([]);
    setQualifiedCompanies([]);
    setPipelineProgress(null);
    setPipelineSummary(null);
    setPipelineStartTime(0);
    setExtractedContext(null);
    setEnrichedContacts(new Map());
    setEnrichDone(false);
    setIsPipelineRunning(false);
    setSearchId(null);
  }, []);

  /* ── Launch search ── */
  const launchSearch = useCallback(
    async (ctx: ExtractedContext) => {
      setExtractedContext(ctx);
      setPhase("searching");

      try {
        const response = await fetch("/api/chat/search", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(session?.access_token
              ? { Authorization: `Bearer ${session.access_token}` }
              : {}),
          },
          body: JSON.stringify({
            industry: ctx.industry || "",
            technology_focus: ctx.technologyFocus || "",
            qualifying_criteria: ctx.qualifyingCriteria || "",
            company_profile: ctx.companyProfile || undefined,
            disqualifiers: ctx.disqualifiers || undefined,
          }),
        });

        if (!response.ok) throw new Error("Search failed");
        const data = await response.json();

        setSearchCompanies(data.companies || []);
        setAllSearchCompanies(data.companies || []);
        setPhase("search-complete");
      } catch (err) {
        console.error("Search error:", err);
        setPhase("chat");
        throw err; // let caller handle messaging
      }
    },
    [session],
  );

  /* ── Launch pipeline (SSE) ── */
  const launchPipeline = useCallback(
    async (
      batch: SearchCompany[],
      previousResults: QualifiedCompany[],
      ctx: ExtractedContext | null,
    ) => {
      // Abort any prior stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setSearchCompanies(batch);
      setPhase("qualifying");
      setQualifiedCompanies(previousResults);
      setPipelineProgress(null);
      setPipelineSummary(null);
      setPipelineStartTime(Date.now());
      setIsPipelineRunning(true);

      try {
        const response = await fetch("/api/pipeline/run", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(session?.access_token
              ? { Authorization: `Bearer ${session.access_token}` }
              : {}),
          },
          body: JSON.stringify({
            companies: batch.map((c) => ({
              url: c.url,
              domain: c.domain,
              title: c.title,
              score: c.score,
            })),
            use_vision: true,
            search_context: ctx
              ? {
                  industry: ctx.industry || undefined,
                  company_profile: ctx.companyProfile || undefined,
                  technology_focus: ctx.technologyFocus || undefined,
                  qualifying_criteria: ctx.qualifyingCriteria || undefined,
                  disqualifiers: ctx.disqualifiers || undefined,
                  geographic_region: ctx.geographicRegion || undefined,
                }
              : undefined,
            // Persist chat history alongside the search record
            messages: messagesRef.current.map((m) => ({ role: m.role, content: m.content })),
          }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) throw new Error("Pipeline connection failed");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let completed = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";

          for (const part of parts) {
            const match = part.match(/^data:\s*(.*)/);
            if (!match) continue;

            try {
              const event = JSON.parse(match[1]);

              if (event.type === "progress") {
                setPipelineProgress({
                  index: event.index,
                  total: event.total,
                  phase: event.phase,
                  company: event.company?.title || event.company?.domain || "",
                });
              } else if (event.type === "result") {
                setPipelineProgress(null);
                setQualifiedCompanies((prev) => [...prev, event.company]);
              } else if (event.type === "error" && event.fatal) {
                throw new Error(event.error);
              } else if (event.type === "complete") {
                setPipelineProgress(null);
                if (event.search_id) setSearchId(event.search_id);
                setPipelineSummary((prev) => {
                  if (!prev) return event.summary;
                  return {
                    hot: prev.hot + (event.summary?.hot || 0),
                    review: prev.review + (event.summary?.review || 0),
                    rejected: prev.rejected + (event.summary?.rejected || 0),
                    failed: prev.failed + (event.summary?.failed || 0),
                  };
                });
                setPhase("complete");
                completed = true;
              }
            } catch (parseErr) {
              if (parseErr instanceof Error && parseErr.message) throw parseErr;
            }
          }
        }

        if (!completed) {
          setPhase("complete");
          setPipelineSummary((prev) =>
            prev || { hot: 0, review: 0, rejected: 0, failed: 0 },
          );
        }
      } catch (err) {
        // AbortError is normal when user resets — don't treat as error
        if (err instanceof DOMException && err.name === "AbortError") return;
        console.error("Pipeline error:", err);
        setPhase("search-complete");
        throw err; // let caller handle messaging
      } finally {
        setIsPipelineRunning(false);
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [session],
  );

  /* ── Resume a saved hunt from the DB ── */
  const resumeHunt = useCallback(
    async (savedSearchId: string) => {
      if (!session?.access_token) throw new Error("Not authenticated");

      const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${API}/api/searches/${savedSearchId}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!res.ok) throw new Error("Failed to load hunt");
      const data = await res.json();

      const search = data.search;
      const leads = data.leads || [];

      // Restore context
      setExtractedContext({
        industry: search.industry || null,
        companyProfile: search.company_profile || null,
        technologyFocus: search.technology_focus || null,
        qualifyingCriteria: search.qualifying_criteria || null,
        disqualifiers: null,
        geographicRegion: search.geographic_region || null,
      });

      // Restore messages
      if (Array.isArray(search.messages) && search.messages.length > 0) {
        setMessages(
          search.messages.map((m: { role: string; content: string }) => ({
            id: crypto.randomUUID(),
            role: m.role as "user" | "assistant",
            content: m.content,
            timestamp: Date.now(),
          })),
        );
        // Mark all fields as ready since we already ran a search
        setReadiness({
          industry: true,
          companyProfile: true,
          technologyFocus: true,
          qualifyingCriteria: true,
          isReady: true,
        });
      }

      // Restore qualified leads
      const qualified: QualifiedCompany[] = leads.map(
        (l: {
          company_name: string;
          domain: string;
          website_url: string;
          score: number;
          tier: string;
          hardware_type?: string | null;
          industry_category?: string | null;
          reasoning: string;
          key_signals?: string[];
          red_flags?: string[];
        }) => ({
          title: l.company_name,
          domain: l.domain,
          url: l.website_url,
          score: l.score,
          tier: l.tier as "hot" | "review" | "rejected",
          hardware_type: l.hardware_type,
          industry_category: l.industry_category,
          reasoning: l.reasoning,
          key_signals: l.key_signals || [],
          red_flags: l.red_flags || [],
        }),
      );
      setQualifiedCompanies(qualified);

      // Summary from leads
      const summary = { hot: 0, review: 0, rejected: 0, failed: 0 };
      for (const l of qualified) {
        if (l.tier in summary) summary[l.tier as keyof typeof summary] += 1;
      }
      setPipelineSummary(summary);

      setSearchId(savedSearchId);
      setPhase("complete");
    },
    [session],
  );

  return (
    <HuntContext.Provider
      value={{
        messages,
        setMessages,
        readiness,
        setReadiness,
        phase,
        searchCompanies,
        allSearchCompanies,
        qualifiedCompanies,
        pipelineProgress,
        pipelineSummary,
        pipelineStartTime,
        extractedContext,
        enrichedContacts,
        enrichDone,
        setPhase,
        setSearchCompanies,
        setAllSearchCompanies,
        setQualifiedCompanies,
        setPipelineProgress,
        setPipelineSummary,
        setPipelineStartTime,
        setExtractedContext,
        setEnrichedContacts,
        setEnrichDone,
        launchSearch,
        launchPipeline,
        resetHunt,
        resumeHunt,
        searchId,
        isPipelineRunning,
      }}
    >
      {children}
    </HuntContext.Provider>
  );
}
