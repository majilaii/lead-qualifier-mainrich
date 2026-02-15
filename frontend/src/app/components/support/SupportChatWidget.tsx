"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "../auth/SessionProvider";

type SupportMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const QUICK_QUESTIONS = [
  "How does Hunt qualify leads?",
  "How do plans and quotas work?",
  "How can I resume old hunts?",
  "How does enrichment work?",
];

const STORAGE_MESSAGES_KEY = "support_widget_messages";
const STORAGE_SESSION_KEY = "support_widget_session";

function uid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function SupportChatWidget() {
  const pathname = usePathname();
  const { session } = useAuth();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SupportMessage[]>([
    {
      id: uid(),
      role: "assistant",
      content:
        "I am Hunt Support AI. Ask anything about product workflow, billing, limits, hunts, leads, or troubleshooting.",
    },
  ]);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const hidden = useMemo(() => pathname.startsWith("/chat"), [pathname]);

  useEffect(() => {
    if (hidden) return;
    try {
      const rawMessages = localStorage.getItem(STORAGE_MESSAGES_KEY);
      const rawSession = localStorage.getItem(STORAGE_SESSION_KEY);
      if (rawMessages) {
        const parsed = JSON.parse(rawMessages);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
        }
      }
      if (rawSession) setSessionId(rawSession);
    } catch {
      // ignore storage errors
    }
  }, [hidden]);

  useEffect(() => {
    if (hidden) return;
    try {
      localStorage.setItem(STORAGE_MESSAGES_KEY, JSON.stringify(messages.slice(-20)));
    } catch {
      // ignore storage errors
    }
  }, [messages, hidden]);

  useEffect(() => {
    if (hidden) return;
    try {
      if (sessionId) localStorage.setItem(STORAGE_SESSION_KEY, sessionId);
    } catch {
      // ignore storage errors
    }
  }, [sessionId, hidden]);

  useEffect(() => {
    if (!open) return;
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, open]);

  if (hidden) return null;

  async function ask(question: string) {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setInput("");
    setMessages((prev) => [...prev, { id: uid(), role: "user", content: q }]);

    try {
      const headers: HeadersInit = { "Content-Type": "application/json" };
      if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`;

      const response = await fetch("/api/support", {
        method: "POST",
        headers,
        body: JSON.stringify({ question: q, sessionId }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.error || "Support request failed");
      }

      if (data.sessionId) setSessionId(data.sessionId);
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          content: data.answer || "I could not answer that clearly. Try a more specific question.",
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Support request failed";
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          content: `I hit an issue: ${msg}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="fixed bottom-6 right-6 z-[70]">
        <button
          onClick={() => setOpen((v) => !v)}
          className="group relative h-14 w-14 cursor-pointer rounded-2xl border border-secondary/30 bg-gradient-to-br from-secondary to-[#5f6df3] text-void shadow-[0_12px_35px_rgba(99,102,241,0.35)] transition-all duration-300 hover:scale-[1.04] hover:shadow-[0_16px_45px_rgba(99,102,241,0.45)]"
          aria-label="Open support chat"
        >
          <span className="absolute -inset-[3px] rounded-[18px] border border-secondary/20 opacity-0 blur-sm transition-opacity duration-300 group-hover:opacity-100" />
          <span className="text-lg font-bold">?</span>
        </button>
      </div>

      <div
        className={`fixed bottom-24 right-6 z-[80] w-[min(92vw,390px)] overflow-hidden rounded-2xl border border-border-bright bg-surface-1/95 shadow-[0_30px_120px_rgba(0,0,0,0.6)] backdrop-blur-xl transition-all duration-300 ${
          open
            ? "pointer-events-auto translate-y-0 opacity-100"
            : "pointer-events-none translate-y-4 opacity-0"
        }`}
      >
        <div className="relative overflow-hidden border-b border-border px-5 py-4">
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(65% 85% at 85% 0%, rgba(129,140,248,0.28), transparent 70%)",
            }}
          />
          <div className="relative flex items-center justify-between">
            <div>
              <p className="font-mono text-[12px] uppercase tracking-[0.22em] text-secondary/80">
                Support AI
              </p>
              <p className="mt-1 font-sans text-sm text-text-secondary">
                Grounded in Hunt docs
              </p>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="rounded-lg border border-border px-2 py-1 font-mono text-[12px] text-text-muted transition-colors hover:text-text-primary"
            >
              Close
            </button>
          </div>
        </div>

        <div ref={scrollerRef} className="max-h-[54vh] min-h-[360px] space-y-3 overflow-y-auto px-4 py-4">
          {messages.map((m) => (
            <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={`max-w-[88%] rounded-2xl px-3 py-2.5 ${
                  m.role === "user"
                    ? "border border-border-bright bg-surface-3 text-text-primary"
                    : "border border-border bg-surface-2/85 text-text-secondary"
                }`}
              >
                <p className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{m.content}</p>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="rounded-2xl border border-border bg-surface-2 px-3 py-2.5">
                <p className="font-mono text-[12px] uppercase tracking-[0.2em] text-text-dim">
                  Thinking...
                </p>
              </div>
            </div>
          )}

          {!loading && (
            <div className="grid grid-cols-1 gap-2">
              {QUICK_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => ask(q)}
                  className="cursor-pointer rounded-xl border border-border bg-surface-2 px-3 py-2 text-left font-sans text-sm text-text-muted transition-colors hover:border-secondary/30 hover:text-text-secondary"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-border bg-surface-1 px-4 py-3">
          <div className="flex items-end gap-2 rounded-xl border border-border bg-surface-2 px-3 py-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about Hunt features, pricing, or workflow..."
              className="max-h-32 min-h-[44px] flex-1 resize-none bg-transparent font-sans text-sm text-text-primary outline-none placeholder:text-text-dim"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void ask(input);
                }
              }}
            />
            <button
              onClick={() => void ask(input)}
              disabled={!input.trim() || loading}
              className="h-9 rounded-lg bg-text-primary px-3 font-mono text-[12px] uppercase tracking-[0.16em] text-void transition-colors hover:bg-white/85 disabled:cursor-not-allowed disabled:opacity-35"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
