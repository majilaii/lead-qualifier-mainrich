"use client";

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type KeyboardEvent,
} from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import UsageMeter from "../UsageMeter";
import { usePipeline } from "../hunt/PipelineContext";
import { useAuth } from "../auth/SessionProvider";
import { useBilling } from "../billing/BillingProvider";
import OnboardingOverlay, { useFirstVisit } from "../onboarding/OnboardingOverlay";
import type {
  ChatMessage,
  ExtractedContext,
  SearchCompany,
  QualifiedCompany,
  PipelineProgress,
  PipelineSummary,
  EnrichedContact,
  Phase,
  Readiness,
} from "../hunt/PipelineContext";

/* Lazy-load the map so mapbox-gl only downloads when needed */
const LiveMapPanel = dynamic(() => import("./LiveMapPanel"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-void">
      <div className="w-6 h-6 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
    </div>
  ),
});

/* ══════════════════════════════════════════════
   Types (pipeline types imported from PipelineContext)
   ══════════════════════════════════════════════ */

// Use ChatMessage as Message alias for internal use
type Message = ChatMessage;

function escapeCsvField(value: string): string {
  if (!value) return "";
  // If field contains comma, quote, or newline — wrap in quotes and escape inner quotes
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function exportToCsv(companies: QualifiedCompany[], filename?: string, enrichedContacts?: Map<string, EnrichedContact>) {
  const hasEnrichment = enrichedContacts && enrichedContacts.size > 0;

  const headers = [
    "Tier",
    "Score",
    "Company",
    "Domain",
    "URL",
    "Company Type",
    "Industry",
    "Reasoning",
    "Key Signals",
    "Red Flags",
    ...(hasEnrichment ? ["Contact Email", "Contact Job Title", "Contact Source"] : []),
  ];

  const rows = companies
    .sort((a, b) => b.score - a.score)
    .map((c) => {
      const contact = enrichedContacts?.get(c.domain);
      return [
        c.tier.toUpperCase(),
        String(c.score),
        escapeCsvField(c.title),
        c.domain,
        c.url,
        escapeCsvField(c.hardware_type || ""),
        escapeCsvField(c.industry_category || ""),
        escapeCsvField(c.reasoning),
        escapeCsvField(c.key_signals.join("; ")),
        escapeCsvField(c.red_flags.join("; ")),
        ...(hasEnrichment
          ? [
              escapeCsvField(contact?.email || ""),
              escapeCsvField(contact?.job_title || ""),
              escapeCsvField(contact?.source || ""),
            ]
          : []),
      ];
    });

  const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `hunt-leads-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function DownloadButton({
  companies,
  label,
  variant = "secondary",
  enrichedContacts,
}: {
  companies: QualifiedCompany[];
  label?: string;
  variant?: "primary" | "secondary";
  enrichedContacts?: Map<string, EnrichedContact>;
}) {
  return (
    <button
      onClick={() => exportToCsv(companies, undefined, enrichedContacts)}
      disabled={companies.length === 0}
      className={`inline-flex items-center gap-1.5 font-mono text-[12px] uppercase tracking-[0.15em] px-3 py-1.5 rounded-lg transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed ${
        variant === "primary"
          ? "bg-text-primary text-void hover:bg-white/85"
          : "border border-border-dim text-text-muted hover:text-text-secondary hover:border-border"
      }`}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      {label || `CSV (${companies.length})`}
    </button>
  );
}

const SUGGESTIONS = [
  { text: "Find US companies importing custom metal fabrication parts" },
  { text: "Consumer electronics brands looking for OEM component suppliers" },
  { text: "European EV companies that need battery or motor components" },
  { text: "Construction equipment manufacturers in Southeast Asia" },
];

/* ══════════════════════════════════════════════
   Shared Sub-Components
   ══════════════════════════════════════════════ */

function ReadinessTracker({ readiness }: { readiness: Readiness }) {
  const steps: { key: keyof Readiness; label: string }[] = [
    { key: "industry", label: "Industry" },
    { key: "companyProfile", label: "Profile" },
    { key: "technologyFocus", label: "Technology" },
    { key: "qualifyingCriteria", label: "Criteria" },
    { key: "isReady", label: "Search" },
  ];

  return (
    <div className="hidden md:flex items-center gap-1.5">
      {steps.map((step, i) => {
        const done = readiness[step.key];
        return (
          <div key={step.key} className="flex items-center gap-1.5">
            {i > 0 && (
              <div className={`w-3 h-px transition-colors duration-500 ${done ? "bg-secondary/40" : "bg-border-dim"}`} />
            )}
            <div className="flex items-center gap-1">
              <div className={`w-1.5 h-1.5 rounded-full transition-all duration-500 ${done ? "bg-secondary shadow-[0_0_6px_rgba(129,140,248,0.4)]" : "bg-border"}`} />
              <span className={`font-mono text-[12px] uppercase tracking-[0.15em] transition-colors duration-500 ${done ? "text-secondary/70" : "text-text-dim"}`}>
                {step.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 animate-slide-up">
      <div className="w-6 h-6 rounded-md flex items-center justify-center bg-secondary/10 text-secondary text-xs flex-shrink-0 mt-0.5">◈</div>
      <div className="flex items-center gap-1.5 py-3">
        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-typing-dot" style={{ animationDelay: "0ms" }} />
        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-typing-dot" style={{ animationDelay: "200ms" }} />
        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-typing-dot" style={{ animationDelay: "400ms" }} />
      </div>
    </div>
  );
}

function MessageContent({ content }: { content: string }) {
  return (
    <div className="space-y-1.5 prose-sm prose-invert max-w-none">
      <ReactMarkdown
        rehypePlugins={[rehypeSanitize]}
        components={{
          p: ({ children }) => <p className="my-1">{children}</p>,
          strong: ({ children }) => (
            <strong className="text-text-primary font-medium">{children}</strong>
          ),
          ol: ({ children }) => <ol className="list-none space-y-1 pl-0.5">{children}</ol>,
          ul: ({ children }) => <ul className="list-none space-y-1 pl-0.5">{children}</ul>,
          li: ({ children, ...props }) => {
            const ordered = (props as Record<string, unknown>).ordered as boolean | undefined;
            const index = (props as Record<string, unknown>).index as number | undefined;
            return (
              <div className="flex gap-2.5">
                {ordered ? (
                  <span className="text-secondary/50 font-mono text-xs mt-px min-w-[1rem] text-right">
                    {(index ?? 0) + 1}.
                  </span>
                ) : (
                  <span className="text-secondary/50 mt-1.5">
                    <svg width="4" height="4" viewBox="0 0 4 4">
                      <circle cx="2" cy="2" r="2" fill="currentColor" />
                    </svg>
                  </span>
                )}
                <span>{children}</span>
              </div>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/* ── Quota CTA — inline upgrade card shown when limit is hit ── */
const QUOTA_CTA_PREFIX = "__QUOTA_CTA__";

function QuotaCTACard({ payload }: { payload: string }) {
  const { checkout } = useBilling();
  let data: { used?: number; limit?: number; label?: string; plan?: string } = {};
  try { data = JSON.parse(payload); } catch { /* ignore */ }

  const { used = "?", limit = "?", label = "items", plan = "Free" } = data;

  return (
    <div className="animate-slide-up">
      <div className="flex items-start gap-3">
        <div className="w-6 h-6 rounded-md flex items-center justify-center bg-amber-500/10 text-amber-400 text-xs flex-shrink-0 mt-0.5">⚠</div>
        <div className="space-y-3 w-full max-w-md">
          {/* Quota message */}
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
            <p className="text-sm text-text-primary font-medium">Quota reached</p>
            <p className="text-xs text-text-muted mt-1">
              You&apos;ve used <span className="text-amber-400 font-mono font-medium">{String(used)}/{String(limit)}</span> {label} this month on the <span className="capitalize font-medium text-text-secondary">{plan}</span> plan.
            </p>
          </div>

          {/* CTA cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {/* Pro */}
            <button
              onClick={() => checkout("pro")}
              className="group relative rounded-xl border border-secondary/30 bg-secondary/5 hover:bg-secondary/10 px-4 py-3 text-left transition-all duration-200 cursor-pointer"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono text-xs font-bold text-secondary tracking-wide">PRO</span>
                <span className="font-mono text-xs text-text-muted">$20<span className="text-text-muted/50">/mo</span></span>
              </div>
              <ul className="space-y-1 text-[12px] text-text-muted">
                <li className="flex items-center gap-1.5"><span className="text-secondary">✓</span> 20 hunts / month</li>
                <li className="flex items-center gap-1.5"><span className="text-secondary">✓</span> 100 leads per hunt</li>
                <li className="flex items-center gap-1.5"><span className="text-secondary">✓</span> 200 enrichments</li>
                <li className="flex items-center gap-1.5"><span className="text-secondary">✓</span> Deep research</li>
              </ul>
              <div className="mt-2.5 text-center text-[12px] font-mono font-medium text-secondary group-hover:underline tracking-wide">
                Upgrade to Pro →
              </div>
            </button>

            {/* Enterprise */}
            <button
              onClick={() => checkout("enterprise")}
              className="group relative rounded-xl border border-amber-400/30 bg-amber-400/5 hover:bg-amber-400/10 px-4 py-3 text-left transition-all duration-200 cursor-pointer"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono text-xs font-bold text-amber-400 tracking-wide">ENTERPRISE</span>
                <span className="font-mono text-xs text-text-muted">$50<span className="text-text-muted/50">/mo</span></span>
              </div>
              <ul className="space-y-1 text-[12px] text-text-muted">
                <li className="flex items-center gap-1.5"><span className="text-amber-400">✓</span> Unlimited hunts</li>
                <li className="flex items-center gap-1.5"><span className="text-amber-400">✓</span> 500 leads per hunt</li>
                <li className="flex items-center gap-1.5"><span className="text-amber-400">✓</span> 1,000 enrichments</li>
                <li className="flex items-center gap-1.5"><span className="text-amber-400">✓</span> Priority support</li>
              </ul>
              <div className="mt-2.5 text-center text-[12px] font-mono font-medium text-amber-400 group-hover:underline tracking-wide">
                Upgrade to Enterprise →
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const isQuotaCTA = !isUser && message.content.startsWith(QUOTA_CTA_PREFIX);

  if (isQuotaCTA) {
    return <QuotaCTACard payload={message.content.slice(QUOTA_CTA_PREFIX.length)} />;
  }

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} animate-slide-up`}>
      <div className={`flex items-start gap-3 max-w-[88%] md:max-w-[75%] ${isUser ? "flex-row-reverse" : ""}`}>
        {!isUser && (
          <div className="w-6 h-6 rounded-md flex items-center justify-center bg-secondary/10 text-secondary text-xs flex-shrink-0 mt-0.5">◈</div>
        )}
        <div className={`rounded-2xl px-4 py-3 ${isUser ? "bg-surface-3 border border-border text-text-primary font-sans text-sm" : "text-text-secondary font-sans text-sm leading-relaxed"}`}>
          {isUser ? <p className="whitespace-pre-wrap">{message.content}</p> : <MessageContent content={message.content} />}
        </div>
      </div>
    </div>
  );
}

interface SavedTemplate {
  id: string;
  name: string;
  search_context: Record<string, string | null>;
}

function WelcomeScreen({ onSuggestionClick, templates, onSelectTemplate }: {
  onSuggestionClick: (text: string) => void;
  templates?: SavedTemplate[];
  onSelectTemplate?: (t: SavedTemplate) => void;
}) {
  return (
    <div className="flex flex-col items-center justify-start h-full px-4 py-12">
      <div className="animate-slide-up flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-secondary/10 border border-secondary/20 flex items-center justify-center text-secondary text-2xl mb-6">◈</div>
        <h1 className="font-mono text-xl md:text-2xl font-bold text-text-primary tracking-tight mb-2 text-center">What are you hunting?</h1>
        <p className="font-sans text-sm text-text-muted mb-10 text-center max-w-md leading-relaxed">
          Describe your ideal customer. I&apos;ll ask a few follow-up questions to sharpen the search, then find matching companies across the web.
        </p>

        {/* Saved ICP Templates */}
        {templates && templates.length > 0 && onSelectTemplate && (
          <div className="w-full max-w-lg mb-6">
            <p className="font-mono text-[12px] text-text-muted uppercase tracking-[0.15em] mb-2.5">Saved ICP Templates</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => onSelectTemplate(t)}
                  className="text-left bg-secondary/5 border border-secondary/15 hover:border-secondary/30 hover:bg-secondary/10 rounded-xl px-4 py-3 transition-all duration-200 group cursor-pointer"
                >
                  <p className="font-mono text-xs text-secondary font-medium truncate">{t.name}</p>
                  <p className="font-sans text-[12px] text-text-dim mt-0.5 truncate">
                    {[t.search_context.industry, t.search_context.technologyFocus || t.search_context.technology_focus].filter(Boolean).join(" · ") || "Custom template"}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
          {SUGGESTIONS.map((s) => (
            <button key={s.text} onClick={() => onSuggestionClick(s.text)} className="text-left bg-surface-2 border border-border hover:border-secondary/30 hover:bg-surface-3 rounded-xl px-4 py-3.5 transition-all duration-200 group cursor-pointer">
              <p className="font-sans text-xs text-text-muted group-hover:text-text-secondary transition-colors leading-relaxed">{s.text}</p>
            </button>
          ))}
        </div>
        <div className="mt-8 w-full max-w-lg">
          <UsageMeter />
        </div>
      </div>
    </div>
  );
}

function ChatInput({ onSend, isLoading }: { onSend: (text: string) => void; isLoading: boolean }) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (ta) { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 200) + "px"; }
  }, []);

  useEffect(() => { adjustHeight(); }, [input, adjustHeight]);
  useEffect(() => { textareaRef.current?.focus(); }, []);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }, [input, isLoading, onSend]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }, [handleSend]);

  return (
    <div className="border-t border-border-dim bg-surface-1/80 backdrop-blur-md px-4 py-5 flex-shrink-0">
      <div className="max-w-3xl mx-auto">
        <div className="relative flex items-end bg-surface-2 border border-border rounded-2xl focus-within:border-secondary/30 transition-colors duration-200">
          <textarea ref={textareaRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} placeholder="Describe your ideal customer..." rows={2} disabled={isLoading} className="flex-1 bg-transparent text-text-primary font-sans text-sm px-4 py-4 resize-none outline-none placeholder:text-text-dim disabled:opacity-50 max-h-[200px]" />
          <button onClick={handleSend} disabled={!input.trim() || isLoading} className="flex-shrink-0 m-2 p-2 rounded-xl bg-text-primary text-void disabled:opacity-15 disabled:cursor-not-allowed hover:bg-white/85 transition-all duration-200 cursor-pointer" aria-label="Send message">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
          </button>
        </div>
        <p className="font-mono text-[12px] text-text-dim mt-2 text-center select-none">Enter to send · Shift+Enter for newline</p>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════
   Pipeline Phase Components
   ══════════════════════════════════════════════ */

function SearchActionCard({ onLaunch, onSaveTemplate }: { onLaunch: () => void; onSaveTemplate?: () => void }) {
  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-secondary/20 rounded-2xl p-5 mt-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-secondary text-sm">◈</span>
          <span className="font-mono text-[12px] uppercase tracking-[0.2em] text-secondary/60">Ready to search</span>
        </div>
        <p className="font-sans text-sm text-text-secondary mb-4">
          I have enough context to find matching companies. Click below to generate search queries and scan the web.
        </p>
        <div className="flex items-center gap-3">
          <button onClick={onLaunch} className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-6 py-3 rounded-xl hover:bg-white/85 transition-colors cursor-pointer">
            Launch Search
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
          </button>
          {onSaveTemplate && (
            <button onClick={onSaveTemplate} className="inline-flex items-center gap-1.5 border border-border-dim hover:border-secondary/30 text-text-muted hover:text-secondary font-mono text-[12px] uppercase tracking-[0.15em] px-4 py-3 rounded-xl transition-colors cursor-pointer">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" /></svg>
              Save as ICP Template
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function SearchingCard() {
  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-border rounded-2xl p-5 mt-4">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-5 h-5 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin" />
          <span className="font-mono text-xs text-secondary">Generating queries &amp; searching...</span>
        </div>
        <div className="space-y-2">
          <div className="h-2 bg-surface-3 rounded-full overflow-hidden">
            <div className="h-full bg-secondary/30 rounded-full animate-pulse" style={{ width: "60%" }} />
          </div>
          <p className="font-sans text-xs text-text-dim">Generating semantic queries via AI, then searching across the web with Exa...</p>
        </div>
      </div>
    </div>
  );
}

function SearchResultsCard({
  companies,
  onQualify,
}: {
  companies: SearchCompany[];
  onQualify: (count: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? companies : companies.slice(0, 8);
  const remaining = companies.length - 8;
  const topN = Math.min(10, companies.length);
  const hasMany = companies.length > 12;

  // Estimate time: ~35s per company
  const estTop = Math.ceil((topN * 35) / 60);
  const estAll = Math.ceil((companies.length * 35) / 60);

  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-border rounded-2xl overflow-hidden mt-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border-dim">
          <div className="flex items-center gap-2">
            <span className="text-secondary text-sm">◈</span>
            <span className="font-mono text-xs text-text-primary">Found {companies.length} companies</span>
          </div>
          <span className="font-mono text-[12px] uppercase tracking-[0.2em] text-text-dim">Exa AI · sorted by relevance</span>
        </div>

        {/* Company list */}
        <div className="divide-y divide-border-dim max-h-[320px] overflow-y-auto">
          {shown.map((c, i) => (
            <div key={c.domain} className="px-5 py-3 hover:bg-surface-3/50 transition-colors">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-mono text-[12px] text-text-dim min-w-[1.2rem] text-right">{i + 1}.</span>
                <img src={`https://www.google.com/s2/favicons?domain=${c.domain}&sz=32`} alt="" width={14} height={14} className="rounded-sm flex-shrink-0" loading="lazy" />
                <span className="font-mono text-[12px] text-secondary/60">{c.domain}</span>
                {c.score != null && (
                  <span className="font-mono text-[12px] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{(c.score * 100).toFixed(0)}%</span>
                )}
              </div>
              <p className="font-sans text-xs text-text-secondary leading-relaxed line-clamp-2 pl-[1.7rem]">
                {c.title}{c.snippet ? ` — ${c.snippet}` : ""}
              </p>
            </div>
          ))}
        </div>

        {remaining > 0 && !expanded && (
          <button onClick={() => setExpanded(true)} className="w-full px-5 py-2 text-center font-mono text-[12px] text-text-muted hover:text-text-secondary border-t border-border-dim hover:bg-surface-3/50 transition-colors cursor-pointer">
            + {remaining} more companies
          </button>
        )}

        {/* Batch size buttons */}
        <div className="px-5 py-4 border-t border-border-dim bg-surface-1/50">
          <div className="flex flex-wrap items-center gap-2.5">
            {hasMany && (
              <button
                onClick={() => onQualify(topN)}
                className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-xl hover:bg-white/85 transition-colors cursor-pointer"
              >
                Top {topN} · ~{estTop} min
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
              </button>
            )}
            <button
              onClick={() => onQualify(companies.length)}
              className={`inline-flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-xl transition-colors cursor-pointer ${
                hasMany
                  ? "bg-surface-3 border border-border text-text-secondary hover:bg-surface-3/80 hover:border-border-bright"
                  : "bg-text-primary text-void hover:bg-white/85"
              }`}
            >
              {hasMany ? `All ${companies.length}` : `Qualify ${companies.length}`} · ~{estAll} min
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
            </button>
          </div>
          <p className="font-mono text-[12px] text-text-dim mt-2">Crawls each website &amp; scores with AI · highest relevance processed first</p>
        </div>
      </div>
    </div>
  );
}

const TIER_STYLES = {
  hot: { label: "Hot Lead", color: "text-hot", bg: "bg-hot/10", border: "border-hot/20" },
  review: { label: "Review", color: "text-review", bg: "bg-review/10", border: "border-review/20" },
  rejected: { label: "Rejected", color: "text-rejected", bg: "bg-surface-3", border: "border-border" },
};

function LiveResultsView({
  progress,
  qualifiedCompanies,
  searchCompanies,
  startTime,
}: {
  progress: PipelineProgress | null;
  qualifiedCompanies: QualifiedCompany[];
  searchCompanies: SearchCompany[];
  startTime: number;
}) {
  const [activeTab, setActiveTab] = useState<"results" | "queue">("results");
  const [expandedCompany, setExpandedCompany] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  // Tick every second so the ETA stays live
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const total = searchCompanies.length;
  const done = qualifiedCompanies.length;
  const remaining = total - done;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  // Live ETA calculation
  const elapsed = (now - startTime) / 1000;
  const avgPerCompany = done > 0 ? elapsed / done : 35;
  const etaSeconds = Math.max(0, Math.ceil(remaining * avgPerCompany));
  const etaMin = Math.floor(etaSeconds / 60);
  const etaSec = etaSeconds % 60;
  const etaStr = remaining <= 0 ? "finishing…" : etaMin > 0 ? `~${etaMin}m ${etaSec}s` : `~${etaSec}s`;

  // Live tier counts
  const hotCount = qualifiedCompanies.filter((c) => c.tier === "hot").length;
  const reviewCount = qualifiedCompanies.filter((c) => c.tier === "review").length;

  // Sort results: hot first, then by score descending
  const sortedResults = [...qualifiedCompanies].sort((a, b) => {
    if (a.tier === "hot" && b.tier !== "hot") return -1;
    if (b.tier === "hot" && a.tier !== "hot") return 1;
    return b.score - a.score;
  });

  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-border rounded-2xl overflow-hidden mt-4">
        {/* Progress header */}
        <div className="px-5 py-3 border-b border-border-dim">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin" />
              <span className="font-mono text-xs text-text-primary">Qualifying leads</span>
            </div>
            <div className="flex items-center gap-3">
              {hotCount > 0 && <span className="font-mono text-[12px] text-hot">{hotCount} hot</span>}
              {reviewCount > 0 && <span className="font-mono text-[12px] text-review">{reviewCount} review</span>}
              <span className="font-mono text-xs text-text-muted">{done}/{total}</span>
              <span className="font-mono text-[12px] text-text-dim">{etaStr}</span>
              {done >= 2 && <DownloadButton companies={qualifiedCompanies} label="CSV" />}
            </div>
          </div>
          <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
            <div className="h-full bg-secondary rounded-full transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-border-dim">
          <button
            onClick={() => setActiveTab("results")}
            className={`flex-1 px-4 py-2 font-mono text-[12px] uppercase tracking-[0.15em] transition-colors cursor-pointer ${
              activeTab === "results"
                ? "text-secondary border-b-2 border-secondary bg-secondary/5"
                : "text-text-dim hover:text-text-muted"
            }`}
          >
            Results ({done})
          </button>
          <button
            onClick={() => setActiveTab("queue")}
            className={`flex-1 px-4 py-2 font-mono text-[12px] uppercase tracking-[0.15em] transition-colors cursor-pointer ${
              activeTab === "queue"
                ? "text-secondary border-b-2 border-secondary bg-secondary/5"
                : "text-text-dim hover:text-text-muted"
            }`}
          >
            Queue ({remaining})
          </button>
        </div>

        {/* Results tab — interactive, browsable */}
        {activeTab === "results" && (
          <div className="max-h-[450px] overflow-y-auto divide-y divide-border-dim">
            {sortedResults.length === 0 && (
              <div className="px-5 py-8 text-center">
                <p className="font-mono text-xs text-text-dim">Results will appear here as companies are qualified...</p>
                {progress && (
                  <p className="font-mono text-[12px] text-secondary/60 mt-2">
                    Currently {progress.phase === "crawling" ? "crawling" : "analyzing"} {progress.company}
                  </p>
                )}
              </div>
            )}
            {sortedResults.map((c) => {
              const style = TIER_STYLES[c.tier];
              const isExpanded = expandedCompany === c.domain;
              return (
                <div key={c.domain} className="animate-slide-up">
                  <button
                    onClick={() => setExpandedCompany(isExpanded ? null : c.domain)}
                    className="w-full px-5 py-3 flex items-center gap-3 hover:bg-surface-3/50 transition-colors cursor-pointer text-left"
                  >
                    <span className={`font-mono text-xs font-bold min-w-[2rem] text-right ${style.color}`}>{c.score}/100</span>
                    <img src={`https://www.google.com/s2/favicons?domain=${c.domain}&sz=32`} alt="" width={14} height={14} className="rounded-sm flex-shrink-0" loading="lazy" />
                    <span className="font-mono text-[12px] text-text-secondary flex-1 truncate">{c.domain}</span>
                    <span className={`font-mono text-[12px] uppercase tracking-[0.15em] px-2 py-0.5 rounded ${style.bg} ${style.color} ${style.border} border`}>
                      {style.label}
                    </span>
                    <svg
                      width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                      className={`text-text-dim transition-transform duration-200 flex-shrink-0 ${isExpanded ? "rotate-90" : ""}`}
                    >
                      <path d="M9 18l6-6-6-6" />
                    </svg>
                  </button>
                  {isExpanded && (
                    <div className="px-5 pb-3 bg-surface-3/30 border-t border-border-dim">
                      <div className="pl-[2.5rem] pt-2.5 space-y-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <a href={c.url} target="_blank" rel="noopener noreferrer" className="font-mono text-[12px] text-secondary/60 hover:text-secondary transition-colors">
                            {c.url} ↗
                          </a>
                          {c.hardware_type && (
                            <span className="font-mono text-[12px] uppercase tracking-[0.15em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{c.hardware_type}</span>
                          )}
                          {c.industry_category && (
                            <span className="font-mono text-[12px] uppercase tracking-[0.15em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{c.industry_category}</span>
                          )}
                        </div>
                        <p className="font-sans text-xs text-text-muted leading-relaxed">{c.reasoning}</p>
                        {c.key_signals.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {c.key_signals.map((s, i) => (
                              <span key={i} className="font-mono text-[12px] text-secondary/50 bg-secondary/5 border border-secondary/10 rounded px-1.5 py-0.5">{s}</span>
                            ))}
                          </div>
                        )}
                        {c.red_flags.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {c.red_flags.map((f, i) => (
                              <span key={i} className="font-mono text-[12px] text-red-400/60 bg-red-400/5 border border-red-400/10 rounded px-1.5 py-0.5">{f}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Queue tab — shows what's processing / pending */}
        {activeTab === "queue" && (
          <div className="max-h-[450px] overflow-y-auto divide-y divide-border-dim">
            {/* Currently processing */}
            {progress && (
              <div className="px-5 py-2.5 flex items-center gap-3 bg-secondary/5">
                <div className="w-3 h-3 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin min-w-[2rem] flex items-center justify-center" />
                <span className="font-mono text-[12px] text-secondary flex-1 truncate">{progress.company}</span>
                <span className="font-mono text-[12px] uppercase tracking-[0.15em] text-secondary/50">
                  {progress.phase === "crawling" ? "Crawling..." : "Qualifying..."}
                </span>
              </div>
            )}
            {/* Pending */}
            {searchCompanies.slice(done + (progress ? 1 : 0)).map((c, i) => (
              <div key={c.domain} className="px-5 py-2.5 flex items-center gap-3 opacity-40">
                <span className="font-mono text-[12px] min-w-[2rem] text-right text-text-dim">{done + (progress ? 1 : 0) + i + 1}</span>
                <img src={`https://www.google.com/s2/favicons?domain=${c.domain}&sz=32`} alt="" width={14} height={14} className="rounded-sm flex-shrink-0" loading="lazy" />
                <span className="font-mono text-[12px] text-text-dim flex-1 truncate">{c.domain}</span>
              </div>
            ))}
            {remaining === 0 && !progress && (
              <div className="px-5 py-6 text-center">
                <p className="font-mono text-xs text-text-dim">All companies processed</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ResultsSummaryCard({ qualifiedCompanies, summary, remainingCount, onContinue, enrichedContacts, setEnrichedContacts, enrichDone, setEnrichDone }: {
  qualifiedCompanies: QualifiedCompany[];
  summary: PipelineSummary;
  remainingCount: number;
  onContinue: (count: number) => void;
  enrichedContacts: Map<string, EnrichedContact>;
  setEnrichedContacts: React.Dispatch<React.SetStateAction<Map<string, EnrichedContact>>>;
  enrichDone: boolean;
  setEnrichDone: React.Dispatch<React.SetStateAction<boolean>>;
}) {
  const { session } = useAuth();
  const [expandedTier, setExpandedTier] = useState<string | null>("hot");

  // Enrichment progress (local — fine to reset)
  const [enriching, setEnriching] = useState(false);
  const [enrichError, setEnrichError] = useState<string | null>(null);
  const [enrichProgress, setEnrichProgress] = useState<{ index: number; total: number } | null>(null);

  const hot = qualifiedCompanies.filter((c) => c.tier === "hot").sort((a, b) => b.score - a.score);
  const review = qualifiedCompanies.filter((c) => c.tier === "review").sort((a, b) => b.score - a.score);
  const rejected = qualifiedCompanies.filter((c) => c.tier === "rejected").sort((a, b) => b.score - a.score);
  const nonRejected = qualifiedCompanies.filter((c) => c.tier !== "rejected").sort((a, b) => b.score - a.score);

  // Enrich hot leads (and optionally review)
  const enrichLeads = useCallback(async (companies: QualifiedCompany[]) => {
    if (companies.length === 0) return;
    setEnriching(true);
    setEnrichDone(false);
    setEnrichError(null);
    setEnrichProgress({ index: 0, total: companies.length });

    try {
      const response = await fetch(`/api/enrich`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(session?.access_token
            ? { Authorization: `Bearer ${session.access_token}` }
            : {}),
        },
        body: JSON.stringify({
          companies: companies.map((c) => ({
            domain: c.domain,
            title: c.title,
            url: c.url,
          })),
        }),
      });

      if (!response.ok || !response.body) {
        const errText = await response.text().catch(() => "");
        console.error("Enrichment failed:", response.status, errText);
        setEnrichError(
          response.status === 401
            ? "Authentication expired — please refresh the page"
            : response.status === 429
              ? "Enrichment quota exceeded — upgrade your plan"
              : `Enrichment failed (${response.status})`
        );
        setEnriching(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
              setEnrichProgress({ index: event.index, total: event.total });
            } else if (event.type === "result" && event.contact) {
              setEnrichedContacts((prev) => {
                const next = new Map(prev);
                next.set(event.contact.domain, event.contact);
                return next;
              });
              setEnrichProgress({ index: event.index + 1, total: event.total });
            } else if (event.type === "complete") {
              setEnriching(false);
              setEnrichDone(true);
              setEnrichProgress(null);
            }
          } catch {
            // Skip unparseable
          }
        }
      }
    } catch (err) {
      console.error("Enrichment error:", err);
      setEnrichError("Network error — check your connection");
      setEnriching(false);
    }
  }, [session]);

  const tiers = [
    { key: "hot", label: "Hot Leads", companies: hot, count: summary.hot },
    { key: "review", label: "Needs Review", companies: review, count: summary.review },
    { key: "rejected", label: "Rejected", companies: rejected, count: summary.rejected },
  ];

  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-border rounded-2xl overflow-hidden mt-4">
        {/* Summary header */}
        <div className="px-5 py-4 border-b border-border-dim">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-secondary text-sm">◈</span>
              <span className="font-mono text-xs text-text-primary font-semibold">Qualification Complete</span>
            </div>
            <div className="flex items-center gap-2">
              {hot.length > 0 && (
                <DownloadButton companies={hot} label={`Hot leads (${hot.length})`} variant="primary" enrichedContacts={enrichedContacts} />
              )}
              {nonRejected.length > hot.length && (
                <DownloadButton companies={nonRejected} label={`Hot + Review (${nonRejected.length})`} enrichedContacts={enrichedContacts} />
              )}
              <DownloadButton companies={qualifiedCompanies} label={`All (${qualifiedCompanies.length})`} enrichedContacts={enrichedContacts} />
            </div>
          </div>
          <div className="flex items-center gap-4 font-mono text-xs">
            <span className="text-hot">{summary.hot} hot</span>
            <span className="text-border-bright">|</span>
            <span className="text-review">{summary.review} review</span>
            <span className="text-border-bright">|</span>
            <span className="text-text-muted">{summary.rejected} rejected</span>
            {summary.failed > 0 && (
              <>
                <span className="text-border-bright">|</span>
                <span className="text-text-dim">{summary.failed} failed</span>
              </>
            )}
          </div>
        </div>

        {/* Tier sections */}
        <div className="divide-y divide-border-dim">
          {tiers.map((tier) => {
            if (tier.count === 0) return null;
            const isExpanded = expandedTier === tier.key;
            const style = TIER_STYLES[tier.key as keyof typeof TIER_STYLES];

            return (
              <div key={tier.key}>
                <button
                  onClick={() => setExpandedTier(isExpanded ? null : tier.key)}
                  className="w-full px-5 py-3 flex items-center justify-between hover:bg-surface-3/50 transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-text-primary">{tier.label} ({tier.count})</span>
                  </div>
                  <svg
                    width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    className={`text-text-dim transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`}
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>

                {isExpanded && (
                  <div className="border-t border-border-dim divide-y divide-border-dim">
                    {tier.companies.map((c) => {
                      const contact = enrichedContacts.get(c.domain);
                      return (
                      <div key={c.domain} className="px-5 py-3">
                        <div className="flex items-center gap-3 mb-1">
                          <span className={`font-mono text-xs font-bold ${style.color}`}>{c.score}/100</span>
                          <img src={`https://www.google.com/s2/favicons?domain=${c.domain}&sz=32`} alt="" width={14} height={14} className="rounded-sm flex-shrink-0" loading="lazy" />
                          <a href={c.url} target="_blank" rel="noopener noreferrer" className="font-mono text-[12px] text-secondary/60 hover:text-secondary transition-colors">
                            {c.domain} ↗
                          </a>
                          {c.hardware_type && (
                            <span className="font-mono text-[12px] uppercase tracking-[0.15em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">
                              {c.hardware_type}
                            </span>
                          )}
                        </div>
                        <p className="font-sans text-xs text-text-muted leading-relaxed mb-1.5">{c.reasoning}</p>
                        {c.key_signals.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {c.key_signals.slice(0, 4).map((s, i) => (
                              <span key={i} className="font-mono text-[12px] text-secondary/50 bg-secondary/5 border border-secondary/10 rounded px-1.5 py-0.5">
                                {s}
                              </span>
                            ))}
                          </div>
                        )}
                        {/* Enriched contact info */}
                        {contact && contact.found && (
                          <div className="mt-2 flex flex-wrap items-center gap-2 bg-secondary/5 border border-secondary/10 rounded-lg px-3 py-2">
                            <span className="font-mono text-[12px] text-secondary/40 uppercase tracking-[0.15em]">Contact</span>
                            {contact.job_title && (
                              <span className="font-mono text-[12px] text-text-secondary">{contact.job_title}</span>
                            )}
                            {contact.email && (
                              <a href={`mailto:${contact.email}`} className="font-mono text-[12px] text-secondary hover:text-secondary/80 transition-colors">
                                {contact.email}
                              </a>
                            )}
                            {contact.phone && (
                              <span className="font-mono text-[12px] text-text-secondary">{contact.phone}</span>
                            )}
                            {contact.source && (
                              <span className={`font-mono text-[12px] px-1 py-0.5 rounded ${contact.source === "website" ? "text-green-400/60 bg-green-500/10" : "text-text-dim bg-surface-3"}`}>
                                {contact.source === "website" ? "✓ scraped free" : contact.source === "hunter" ? "via Hunter.io" : `via ${contact.source}`}
                              </span>
                            )}
                          </div>
                        )}
                        {contact && !contact.found && (
                          <div className="mt-2 font-mono text-[12px] text-text-dim">No contact info found</div>
                        )}
                      </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Contact summary & Hunter.io fallback */}
        {(() => {
          // Contacts already found via free website scraping (Phase 2)
          const scrapedContacts = hot.filter((c) => {
            const contact = enrichedContacts.get(c.domain);
            return contact && contact.found && contact.source === "website";
          });
          // Hot leads still missing contacts
          const hotMissingContacts = hot.filter((c) => {
            const contact = enrichedContacts.get(c.domain);
            return !contact || !contact.found;
          });
          // Non-rejected leads still missing contacts (for "or all qualified" button)
          const nonRejectedMissing = nonRejected.filter((c) => {
            const contact = enrichedContacts.get(c.domain);
            return !contact || !contact.found;
          });

          return (
            <>
              {/* Show scraped contacts summary */}
              {scrapedContacts.length > 0 && (
                <div className="px-5 py-3 border-t border-border-dim bg-green-500/5">
                  <div className="flex items-center gap-2">
                    <span className="text-green-400 text-xs">✓</span>
                    <span className="font-mono text-[12px] text-green-400/70">
                      {scrapedContacts.length} contact{scrapedContacts.length > 1 ? "s" : ""} found via website scraping (free)
                    </span>
                    {hotMissingContacts.length > 0 && (
                      <span className="font-mono text-[12px] text-text-dim ml-1">
                        · {hotMissingContacts.length} still missing
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Hunter.io fallback — only for leads still missing contacts */}
              {hotMissingContacts.length > 0 && !enrichDone && (
                <div className="px-5 py-4 border-t border-border-dim bg-surface-1/50">
                  {enriching && enrichProgress ? (
                    <div className="flex items-center gap-3">
                      <div className="w-5 h-5 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
                      <span className="font-mono text-xs text-text-secondary">
                        Finding contacts... {enrichProgress.index}/{enrichProgress.total}
                      </span>
                      <div className="flex-1 h-1 bg-surface-3 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-secondary/50 rounded-full transition-all duration-300"
                          style={{ width: `${Math.round((enrichProgress.index / enrichProgress.total) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        onClick={() => enrichLeads(hotMissingContacts)}
                        className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-xl hover:bg-secondary/20 hover:border-secondary/40 transition-colors cursor-pointer"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                          <circle cx="12" cy="7" r="4" />
                        </svg>
                        Find contacts for {hotMissingContacts.length} remaining lead{hotMissingContacts.length > 1 ? "s" : ""}
                      </button>
                      {nonRejectedMissing.length > hotMissingContacts.length && (
                        <button
                          onClick={() => enrichLeads(nonRejectedMissing)}
                          className="inline-flex items-center gap-2 font-mono text-[12px] text-text-muted hover:text-secondary uppercase tracking-[0.15em] transition-colors cursor-pointer border border-border-dim hover:border-secondary/30 rounded-lg px-3 py-1.5"
                        >
                          Or all {nonRejectedMissing.length} qualified
                        </button>
                      )}
                      <span className="font-mono text-[12px] text-text-dim">via Hunter.io (paid)</span>
                    </div>
                  )}
                  {enrichError && (
                    <div className="mt-2 font-mono text-[12px] text-red-400">
                      ⚠ {enrichError}
                    </div>
                  )}
                </div>
              )}

              {/* All contacts found — either from scraping, Hunter.io, or both */}
              {(enrichDone || (hot.length > 0 && hotMissingContacts.length === 0)) && (
                <div className="px-5 py-3 border-t border-border-dim bg-secondary/5">
                  <div className="flex items-center gap-2">
                    <span className="text-secondary text-xs">✓</span>
                    <span className="font-mono text-[12px] text-secondary/70">
                      Contacts enriched — {Array.from(enrichedContacts.values()).filter((c) => c.found).length} found
                      {Array.from(enrichedContacts.values()).filter((c) => !c.found).length > 0 &&
                        `, ${Array.from(enrichedContacts.values()).filter((c) => !c.found).length} not found`}
                      {scrapedContacts.length > 0 && ` (${scrapedContacts.length} via free scraping)`}
                    </span>
                  </div>
                </div>
              )}
            </>
          );
        })()}

        {/* Continue with remaining batch */}
        {remainingCount > 0 && (
          <div className="px-5 py-4 border-t border-border-dim bg-surface-1/50">
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={() => onContinue(remainingCount)}
                className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-xl hover:bg-white/85 transition-colors cursor-pointer"
              >
                Continue with remaining {remainingCount}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
              </button>
              <span className="font-mono text-[12px] text-text-dim">~{Math.ceil(remainingCount * 0.6)} min · results will be merged</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════
   Main ChatInterface
   ══════════════════════════════════════════════ */

export default function ChatInterface() {
  const router = useRouter();
  const hunt = usePipeline();
  const { isFirstVisit, checked: onboardingChecked, completeOnboarding } = useFirstVisit();

  // Destructure pipeline state from global context (survives navigation)
  const {
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
    messages,
    setMessages,
    readiness,
    setReadiness,
    setExtractedContext,
    setEnrichedContacts,
    setEnrichDone,
    launchSearch: ctxLaunchSearch,
    launchPipeline: ctxLaunchPipeline,
    resetPipeline,
    showMap,
    setShowMap,
    useMapBounds,
    mapBounds,
    setUseMapBounds,
  } = hunt;

  // Chat-only state (local to this page)
  const [isLoading, setIsLoading] = useState(false);
  const [showMobileMap, setShowMobileMap] = useState(false); // mobile fullscreen map overlay
  const [quotaError, setQuotaError] = useState<{ action: string; used: number; limit: number; plan: string } | null>(null);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  // ── Template state ──
  const { session } = useAuth();
  const [savedTemplates, setSavedTemplates] = useState<SavedTemplate[]>([]);
  const [templatesLoaded, setTemplatesLoaded] = useState(false);
  const [showSaveTemplateDialog, setShowSaveTemplateDialog] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateSaving, setTemplateSaving] = useState(false);

  // Check for ?session= URL param to resume a saved chat
  const searchParams = useSearchParams();
  const resumeSessionId = searchParams.get("session");
  const resumeAttempted = useRef(false);

  useEffect(() => {
    if (!resumeSessionId || resumeAttempted.current) return;
    if (!session?.access_token) return;
    resumeAttempted.current = true;
    hunt.resumeChat(resumeSessionId).catch((err) =>
      console.error("Failed to resume chat session:", err)
    );
  }, [resumeSessionId, session, hunt]);

  // Load templates on mount
  useEffect(() => {
    if (templatesLoaded || !session?.access_token) return;
    setTemplatesLoaded(true);
    fetch("/api/proxy/templates", {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then(setSavedTemplates)
      .catch(() => {});
  }, [session, templatesLoaded]);

  const saveTemplate = useCallback(async () => {
    if (!session?.access_token || !extractedContext || !templateName.trim()) return;
    setTemplateSaving(true);
    try {
      const res = await fetch("/api/proxy/templates", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: templateName.trim(),
          search_context: extractedContext,
        }),
      });
      if (res.ok) {
        const saved = await res.json();
        setSavedTemplates((prev) => [...prev, saved]);
        setShowSaveTemplateDialog(false);
        setTemplateName("");
      }
    } finally {
      setTemplateSaving(false);
    }
  }, [session, extractedContext, templateName]);

  const selectTemplate = useCallback((t: SavedTemplate) => {
    const ctx: ExtractedContext = {
      industry: t.search_context.industry || null,
      companyProfile: t.search_context.companyProfile || null,
      technologyFocus: t.search_context.technologyFocus || t.search_context.technology_focus || null,
      qualifyingCriteria: t.search_context.qualifyingCriteria || t.search_context.qualifying_criteria || null,
      disqualifiers: t.search_context.disqualifiers || null,
      geographicRegion: t.search_context.geographicRegion || t.search_context.geographic_region || null,
      countryCode: t.search_context.countryCode || t.search_context.country_code || null,
      geoBounds: t.search_context.geoBounds || t.search_context.geo_bounds || null,
    };
    setExtractedContext(ctx);
    setReadiness({ industry: true, companyProfile: true, technologyFocus: true, qualifyingCriteria: true, isReady: true });
    setMessages([
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `Loaded template **${t.name}**:\n- Industry: ${ctx.industry || "—"}\n- Technology: ${ctx.technologyFocus || "—"}\n- Criteria: ${ctx.qualifyingCriteria || "—"}\n\nReady to search — click **Launch Search** below.`,
        timestamp: Date.now(),
      },
    ]);
  }, [setExtractedContext, setReadiness, setMessages]);

  // ── Resizable split state ──
  const [splitPercent, setSplitPercent] = useState(40); // chat panel width %
  const isDraggingRef = useRef(false);
  const splitContainerRef = useRef<HTMLDivElement>(null);

  // Drag handlers for the resize divider
  const onDragStart = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const move = (clientX: number) => {
      if (!isDraggingRef.current || !splitContainerRef.current) return;
      const rect = splitContainerRef.current.getBoundingClientRect();
      const pct = ((clientX - rect.left) / rect.width) * 100;
      // Clamp between 20% and 80%
      setSplitPercent(Math.min(80, Math.max(20, pct)));
    };

    const onMouseMove = (ev: MouseEvent) => move(ev.clientX);
    const onTouchMove = (ev: TouchEvent) => move(ev.touches[0].clientX);

    const stop = () => {
      isDraggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", stop);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", stop);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", stop);
    window.addEventListener("touchmove", onTouchMove);
    window.addEventListener("touchend", stop);
  }, []);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, phase, qualifiedCompanies, scrollToBottom]);

  // Reset everything (resetPipeline clears messages, readiness, pipeline state)
  const resetChat = useCallback(() => {
    resetPipeline();
  }, [resetPipeline]);

  // Listen for quota exceeded events from PipelineContext
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setQuotaError(detail);

      // Friendly labels for actions
      const actionLabels: Record<string, string> = { search: "searches", leads: "leads", enrichment: "enrichments" };
      const label = actionLabels[detail.action] ?? `${detail.action}s`;
      const planName = (detail.plan ?? "free").charAt(0).toUpperCase() + (detail.plan ?? "free").slice(1);

      // Render a rich CTA card inline in the chat
      const payload = JSON.stringify({
        used: detail.used ?? 0,
        limit: detail.limit ?? 0,
        label,
        plan: planName,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant" as const,
          content: `${QUOTA_CTA_PREFIX}${payload}`,
          timestamp: Date.now(),
        },
      ]);
    };
    window.addEventListener("hunt:quota_exceeded", handler);
    return () => window.removeEventListener("hunt:quota_exceeded", handler);
  }, [setMessages]);

  // Send chat message
  const sendMessage = useCallback(
    async (content: string) => {
      const userMessage: Message = { id: crypto.randomUUID(), role: "user", content, timestamp: Date.now() };
      const updatedMessages = [...messages, userMessage];
      setMessages(updatedMessages);
      setIsLoading(true);

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: updatedMessages }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => null);
          throw new Error(errData?.error || "Failed to get response");
        }
        const data = await response.json();

        const assistantMessage: Message = { id: crypto.randomUUID(), role: "assistant", content: data.message, timestamp: Date.now() };
        setMessages((prev) => [...prev, assistantMessage]);

        if (data.readiness) setReadiness(data.readiness);
        if (data.extractedContext) setExtractedContext(data.extractedContext);
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "Something went wrong. Please try again.";
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", content: errorMsg, timestamp: Date.now() },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [messages]
  );

  // Launch Exa search (delegates to global context)
  const launchSearch = useCallback(async () => {
    if (!extractedContext) return;
    try {
      await ctxLaunchSearch(extractedContext);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: "Search failed. Please try again.", timestamp: Date.now() },
      ]);
    }
  }, [extractedContext, ctxLaunchSearch]);

  // Launch pipeline (delegates to global context — SSE runs even if you navigate away)
  const launchPipeline = useCallback(async (batchCount: number, continueFromRemaining = false) => {
    const source = continueFromRemaining
      ? allSearchCompanies.filter((c) => !qualifiedCompanies.some((qc) => qc.domain === c.domain))
      : searchCompanies;

    if (source.length === 0) return;

    const sorted = [...source].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    const batch = sorted.slice(0, batchCount);
    const previousResults = continueFromRemaining ? qualifiedCompanies : [];

    try {
      await ctxLaunchPipeline(batch, previousResults, extractedContext);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: "Pipeline encountered an error. You can try again.", timestamp: Date.now() },
      ]);
    }
  }, [searchCompanies, allSearchCompanies, qualifiedCompanies, extractedContext, ctxLaunchPipeline]);

  // Force-launch search with whatever context we have (skip follow-ups)
  const forceSearch = useCallback(async () => {
    const ctx = extractedContext || { industry: null, companyProfile: null, technologyFocus: null, qualifyingCriteria: null, disqualifiers: null, geographicRegion: null, countryCode: null, geoBounds: null };

    if (!ctx.industry && messages.length > 0) {
      const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
      if (lastUserMsg) {
        ctx.industry = lastUserMsg.content;
      }
    }

    setExtractedContext(ctx);
    setReadiness({ industry: true, companyProfile: true, technologyFocus: true, qualifyingCriteria: true, isReady: true });

    try {
      await ctxLaunchSearch(ctx);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: "Search failed. Please try again.", timestamp: Date.now() },
      ]);
    }
  }, [extractedContext, messages, setExtractedContext, ctxLaunchSearch]);

  // Determine if we should show the search action card
  const showSearchAction = readiness.isReady && phase === "chat" && !isLoading;
  // Show "skip & search" when we have at least 1 user message, AI has responded, but isReady is still false
  const showSkipSearch = !readiness.isReady && phase === "chat" && !isLoading && messages.length >= 2;
  // Always show chat input except when actively searching (brief loading state)
  const showChatInput = phase !== "searching";

  // Split layout: map + chat sidebar whenever the user has the map open
  const splitMode = showMap;
  // Whether to show the floating mobile map button
  const showMobileMapBtn = showMap;

  /* ── Chat content (shared between full and split modes) ── */
  const chatContent = (
    <>
      {messages.length === 0 ? (
        <WelcomeScreen onSuggestionClick={sendMessage} templates={savedTemplates} onSelectTemplate={selectTemplate} />
      ) : (
        <div className={`${splitMode ? "" : "max-w-3xl mx-auto"} py-6 px-4 space-y-5`}>
          {/* Chat messages */}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {isLoading && <TypingIndicator />}

          {/* Skip & Search — lets users bypass follow-up questions */}
          {showSkipSearch && (
            <div className={`animate-slide-up ${splitMode ? "" : "max-w-3xl mx-auto"}`}>
              <button
                onClick={forceSearch}
                className="inline-flex items-center gap-2 font-mono text-[12px] text-text-muted hover:text-secondary uppercase tracking-[0.15em] transition-colors duration-200 mt-2 cursor-pointer border border-border-dim hover:border-secondary/30 rounded-lg px-3 py-1.5"
              >
                Skip questions &amp; search now →
              </button>
            </div>
          )}

          {/* Search action card */}
          {showSearchAction && <SearchActionCard onLaunch={launchSearch} onSaveTemplate={() => setShowSaveTemplateDialog(true)} />}

          {/* Searching indicator */}
          {phase === "searching" && <SearchingCard />}

          {/* Search results with batch size control */}
          {phase === "search-complete" && searchCompanies.length > 0 && (
            <SearchResultsCard companies={searchCompanies} onQualify={launchPipeline} />
          )}

          {/* Live interactive results — browse while processing */}
          {phase === "qualifying" && (
            <LiveResultsView
              progress={pipelineProgress}
              qualifiedCompanies={qualifiedCompanies}
              searchCompanies={searchCompanies}
              startTime={pipelineStartTime}
            />
          )}

          {/* Final results */}
          {phase === "complete" && pipelineSummary && (
            <ResultsSummaryCard
              qualifiedCompanies={qualifiedCompanies}
              summary={pipelineSummary}
              remainingCount={allSearchCompanies.filter((c) => !qualifiedCompanies.some((qc) => qc.domain === c.domain)).length}
              onContinue={(count) => launchPipeline(count, true)}
              enrichedContacts={enrichedContacts}
              setEnrichedContacts={setEnrichedContacts}
              enrichDone={enrichDone}
              setEnrichDone={setEnrichDone}
            />
          )}

          <div ref={messagesEndRef} />
        </div>
      )}
    </>
  );

  return (
    <div className="flex flex-col h-dvh bg-void">
      {/* ─── Onboarding Overlay (first visit only) ─── */}
      {onboardingChecked && isFirstVisit && (
        <OnboardingOverlay onComplete={completeOnboarding} />
      )}

      {/* ─── Save Template Dialog ─── */}
      {showSaveTemplateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/80 backdrop-blur-sm">
          <div className="bg-surface-2 border border-border rounded-2xl p-6 w-full max-w-sm mx-4 animate-slide-up">
            <h3 className="font-mono text-sm font-bold text-text-primary mb-1">Save ICP Template</h3>
            <p className="font-sans text-xs text-text-muted mb-4">Save this search profile so you can re-use it later.</p>
            <input
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="e.g. US CNC Manufacturers"
              className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2.5 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 mb-4"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter" && templateName.trim()) saveTemplate(); }}
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setShowSaveTemplateDialog(false); setTemplateName(""); }}
                className="font-mono text-[12px] text-text-muted hover:text-text-primary uppercase tracking-[0.15em] px-4 py-2.5 rounded-lg border border-border hover:border-border-bright transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={saveTemplate}
                disabled={!templateName.trim() || templateSaving}
                className="font-mono text-[12px] text-void bg-text-primary hover:bg-white/85 font-bold uppercase tracking-[0.15em] px-4 py-2.5 rounded-lg transition-colors disabled:opacity-40 cursor-pointer"
              >
                {templateSaving ? "Saving…" : "Save Template"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Header ─── */}
      <header className="flex items-center justify-between px-4 md:px-6 h-14 border-b border-border-dim bg-surface-1/80 backdrop-blur-md flex-shrink-0 z-20">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 group">
            <span className="text-secondary text-xs font-bold">◈</span>
            <span className="text-text-primary text-xs font-semibold tracking-[0.12em] uppercase group-hover:text-secondary transition-colors duration-200">Hunt</span>
          </Link>
          {/* Back to dashboard — always visible */}
          <button
            onClick={() => router.push(localStorage.getItem("lastDashboardTab") || "/dashboard")}
            className="flex items-center gap-1.5 font-mono text-[12px] text-text-muted hover:text-secondary uppercase tracking-[0.15em] transition-colors duration-200 border border-border-dim hover:border-secondary/30 rounded-lg px-2.5 py-1.5 cursor-pointer ml-1"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5" /><path d="M12 19l-7-7 7-7" /></svg>
            Dashboard
          </button>
        </div>

        <div className="flex items-center gap-3">
          {messages.length > 0 && phase === "chat" && <ReadinessTracker readiness={readiness} />}
          {phase !== "chat" && (
            <span className="font-mono text-[12px] uppercase tracking-[0.2em] text-secondary/50">
              {phase === "searching" && "Searching..."}
              {phase === "search-complete" && `${searchCompanies.length} found — ready to qualify`}
              {phase === "qualifying" && "Qualifying..."}
              {phase === "complete" && "Complete"}
            </span>
          )}

          {/* Area locked badge — visible when geo-fence is active */}
          {useMapBounds && mapBounds && (
            <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2.5 py-1 text-emerald-400">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
                <path fillRule="evenodd" d="m7.539 14.841.003.003.002.002a.755.755 0 0 0 .912 0l.002-.002.003-.003.012-.009a5.57 5.57 0 0 0 .19-.153 15.588 15.588 0 0 0 2.046-2.082c1.101-1.362 2.291-3.342 2.291-5.597A5 5 0 0 0 3 7c0 2.255 1.19 4.235 2.291 5.597a15.591 15.591 0 0 0 2.236 2.235l.012.01ZM8 8.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" clipRule="evenodd" />
              </svg>
              <span className="font-mono text-[9px] uppercase tracking-[0.1em]">Area locked</span>
              <button
                onClick={() => setUseMapBounds(false)}
                className="ml-0.5 text-emerald-400/60 hover:text-emerald-300 transition-colors cursor-pointer text-xs leading-none"
                title="Clear geo-fence"
              >
                ✕
              </button>
            </div>
          )}

          {/* Map toggle — always visible */}
          <button
            onClick={() => setShowMap((v) => !v)}
            className={`hidden md:flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors duration-200 border rounded-lg px-2.5 py-1.5 cursor-pointer ${
              showMap
                ? "text-secondary border-secondary/30 bg-secondary/5"
                : "text-text-muted border-border-dim hover:border-secondary/30 hover:text-secondary"
            }`}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
              <line x1="8" y1="2" x2="8" y2="18" />
              <line x1="16" y1="6" x2="16" y2="22" />
            </svg>
            {showMap ? "Hide Map" : "Show Map"}
          </button>
        </div>

        {messages.length > 0 && (
          <button onClick={resetChat} className="font-mono text-[12px] text-text-muted hover:text-text-primary uppercase tracking-[0.15em] transition-colors duration-200 border border-border-dim hover:border-border rounded-lg px-3 py-1.5 cursor-pointer">
            + New Hunt
          </button>
        )}
        {messages.length === 0 && <div />}
      </header>

      {/* ─── Body: split or full ─── */}
      {splitMode ? (
        /* ═══ Split Layout: Chat (left) + Map (right) ═══ */
        <div ref={splitContainerRef} className="flex-1 min-h-0 flex overflow-hidden relative">
          {/* Chat sidebar — left (resizable) */}
          <div
            className="flex-shrink-0 flex flex-col h-full min-w-0 overflow-hidden animate-slide-left relative z-[2]"
            style={{ width: `${splitPercent}%` }}
          >
            {/* Scrollable content */}
            <div
              className="flex-1 min-h-0 overflow-y-auto overscroll-contain"
              style={{ touchAction: "pan-y" }}
            >
              <div>
                {chatContent}
              </div>
            </div>

            {/* Chat input in split mode */}
            {showChatInput && <ChatInput onSend={sendMessage} isLoading={isLoading} />}

            {/* Status bar */}
            <div className="border-t border-border-dim bg-surface-1/80 backdrop-blur-md px-4 py-2 flex-shrink-0">
              <div className="flex items-center justify-between">
                <p className="font-mono text-[12px] text-text-dim">
                  {phase === "search-complete" && `${searchCompanies.length} companies found — qualify them`}
                  {phase === "qualifying" && `Qualifying ${searchCompanies.length} companies`}
                  {phase === "complete" && `Done — ${pipelineSummary?.hot || 0} hot leads found`}
                </p>
                {phase === "complete" && (
                  <button onClick={resetChat} className="font-mono text-[12px] text-secondary hover:text-secondary/80 uppercase tracking-[0.15em] cursor-pointer">
                    New Hunt →
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* ── Drag handle ── */}
          <div
            onMouseDown={onDragStart}
            onTouchStart={onDragStart}
            className="hidden md:flex items-center justify-center w-1.5 cursor-col-resize group hover:bg-secondary/10 active:bg-secondary/15 transition-colors flex-shrink-0 relative z-10"
            title="Drag to resize"
          >
            <div className="w-px h-full bg-border-dim group-hover:bg-secondary/40 group-active:bg-secondary/60 transition-colors" />
          </div>

          {/* Map panel — right (resizable, desktop) */}
          <div
            className="hidden md:flex flex-1 min-w-0 h-full overflow-hidden animate-slide-in-right relative"
          >
            <LiveMapPanel />
          </div>

          {/* Mobile: floating map toggle */}
          {showMobileMapBtn && (
            <>
              <button
                onClick={() => setShowMobileMap(true)}
                className="md:hidden fixed bottom-20 right-4 z-30 w-12 h-12 rounded-full bg-secondary/90 text-void shadow-lg shadow-secondary/20 flex items-center justify-center cursor-pointer hover:bg-secondary transition-colors"
                aria-label="Toggle map"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
                  <line x1="8" y1="2" x2="8" y2="18" />
                  <line x1="16" y1="6" x2="16" y2="22" />
                </svg>
              </button>
              {/* Mobile map overlay */}
              {showMobileMap && (
                <div className="md:hidden fixed inset-0 z-40 bg-void/95 flex flex-col">
                  <div className="flex items-center justify-between px-4 h-12 border-b border-border-dim bg-surface-1/80 backdrop-blur-md flex-shrink-0">
                    <span className="font-mono text-xs text-text-primary">Live Map</span>
                    <button onClick={() => setShowMobileMap(false)} className="font-mono text-xs text-text-muted hover:text-text-primary cursor-pointer px-2 py-1">
                      ✕ Close
                    </button>
                  </div>
                  <div className="flex-1">
                    <LiveMapPanel />
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      ) : (
        /* ═══ Standard Full-Width Layout ═══ */
        <>
          {/* ─── Content ─── */}
          <div className="flex-1 min-h-0 overflow-y-auto flex flex-col">
            <div className="flex-1">
              {chatContent}
            </div>
          </div>

          {/* ─── Input ─── */}
          {showChatInput && <ChatInput onSend={sendMessage} isLoading={isLoading} />}

          {/* Status bar for pipeline phases */}
          {phase !== "chat" && phase !== "searching" && (
            <div className="border-t border-border-dim bg-surface-1/80 backdrop-blur-md px-4 py-2 flex-shrink-0">
              <div className="max-w-3xl mx-auto flex items-center justify-between">
                <p className="font-mono text-[12px] text-text-dim">
                  {phase === "search-complete" && "Review the results above, then qualify them"}
                  {phase === "qualifying" && `Qualifying ${searchCompanies.length} companies — browse results above while you wait`}
                  {phase === "complete" && `Done — ${pipelineSummary?.hot || 0} hot leads found`}
                </p>
                {phase === "complete" && (
                  <button onClick={resetChat} className="font-mono text-[12px] text-secondary hover:text-secondary/80 uppercase tracking-[0.15em] cursor-pointer">
                    New Hunt →
                  </button>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
