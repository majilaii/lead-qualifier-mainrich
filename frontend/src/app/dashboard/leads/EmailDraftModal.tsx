"use client";

import { useState } from "react";
import { useAuth } from "../../components/auth/SessionProvider";

interface Contact {
  full_name: string | null;
  job_title: string | null;
  email: string | null;
}

interface Draft {
  to_name: string;
  to_title: string;
  to_email: string | null;
  subject: string;
  body: string;
  tone: string;
}

interface EmailDraftModalProps {
  leadId: string;
  companyName: string;
  contacts: Contact[];
  onClose: () => void;
}

type Tone = "formal" | "casual" | "consultative";

export default function EmailDraftModal({
  leadId,
  companyName,
  contacts,
  onClose,
}: EmailDraftModalProps) {
  const { session } = useAuth();
  const [tone, setTone] = useState<Tone>("consultative");
  const [senderContext, setSenderContext] = useState(
    () => localStorage.getItem("hunt_sender_context") || ""
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Editable draft fields
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");

  const bestContact = contacts.find((c) => c.email) || contacts[0] || null;

  const generateDraft = async () => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);

    // Save sender context for next time
    if (senderContext.trim()) {
      localStorage.setItem("hunt_sender_context", senderContext.trim());
    }

    try {
      const res = await fetch(`/api/proxy/leads/${leadId}/draft-email`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          tone,
          sender_context: senderContext.trim() || null,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || data.error || "Failed to generate draft");
      }

      const data = await res.json();
      setDraft(data.draft);
      setEditSubject(data.draft.subject);
      setEditBody(data.draft.body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate draft");
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = async () => {
    const text = `Subject: ${editSubject}\n\n${editBody}`;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const openInMailClient = () => {
    const email = draft?.to_email || "";
    const subject = encodeURIComponent(editSubject);
    const body = encodeURIComponent(editBody);
    window.open(`mailto:${email}?subject=${subject}&body=${body}`);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/70 backdrop-blur-sm">
      <div className="bg-surface-2 border border-border rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-dim">
          <h2 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.1em]">
            Draft Email
          </h2>
          <button
            onClick={onClose}
            className="text-text-dim hover:text-text-primary transition-colors cursor-pointer"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Recipient */}
          <div>
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim">To</span>
            <p className="font-mono text-xs text-text-primary mt-1">
              {bestContact?.full_name || "Decision Maker"} at {companyName}
              {bestContact?.job_title && (
                <span className="text-text-dim ml-1">· {bestContact.job_title}</span>
              )}
            </p>
            {bestContact?.email && (
              <p className="font-mono text-[10px] text-text-muted mt-0.5">{bestContact.email}</p>
            )}
            {!bestContact?.email && (
              <p className="font-mono text-[10px] text-amber-400/70 mt-0.5">
                No email found — draft will still be generated
              </p>
            )}
          </div>

          {/* Tone selector */}
          <div>
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim block mb-2">
              Tone
            </span>
            <div className="flex gap-2">
              {(["consultative", "formal", "casual"] as Tone[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTone(t)}
                  className={`flex-1 font-mono text-[10px] uppercase tracking-wider py-2 rounded-lg border transition-colors cursor-pointer ${
                    tone === t
                      ? "bg-secondary/10 border-secondary/30 text-secondary"
                      : "border-border text-text-dim hover:text-text-muted"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Sender context */}
          <div>
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim block mb-2">
              Your context <span className="text-text-dim">(optional, saved for next time)</span>
            </span>
            <textarea
              value={senderContext}
              onChange={(e) => setSenderContext(e.target.value)}
              placeholder="e.g. We manufacture custom NdFeB magnets for industrial applications"
              rows={2}
              className="w-full bg-surface-3 border border-border rounded-lg px-4 py-2.5 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors resize-none"
            />
          </div>

          {/* Generate button */}
          {!draft && (
            <button
              onClick={generateDraft}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-6 py-3.5 rounded-xl hover:bg-white/85 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-void/30 border-t-void rounded-full animate-spin" />
                  Drafting personalized email...
                </>
              ) : (
                <>✉ Generate Draft</>
              )}
            </button>
          )}

          {/* Error */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2.5">
              <p className="font-mono text-[10px] text-red-400">{error}</p>
            </div>
          )}

          {/* Generated draft */}
          {draft && (
            <div className="space-y-4">
              <div className="border-t border-border-dim pt-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim">
                  Subject
                </span>
                <input
                  type="text"
                  value={editSubject}
                  onChange={(e) => setEditSubject(e.target.value)}
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-2.5 font-mono text-xs text-text-primary focus:outline-none focus:border-secondary/40 transition-colors mt-1"
                />
              </div>

              <div>
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim">
                  Body
                </span>
                <textarea
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  rows={8}
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary focus:outline-none focus:border-secondary/40 transition-colors mt-1 resize-y"
                />
              </div>

              {/* Actions */}
              <div className="flex gap-2">
                <button
                  onClick={copyToClipboard}
                  className="flex-1 flex items-center justify-center gap-1.5 font-mono text-[10px] uppercase tracking-wider py-2.5 rounded-lg bg-secondary/10 border border-secondary/20 text-secondary hover:bg-secondary/20 transition-colors cursor-pointer"
                >
                  {copied ? "✓ Copied!" : "📋 Copy to Clipboard"}
                </button>
                {draft.to_email && (
                  <button
                    onClick={openInMailClient}
                    className="flex-1 flex items-center justify-center gap-1.5 font-mono text-[10px] uppercase tracking-wider py-2.5 rounded-lg border border-border text-text-muted hover:text-text-primary hover:border-border-bright transition-colors cursor-pointer"
                  >
                    📧 Open in Mail
                  </button>
                )}
                <button
                  onClick={() => {
                    setDraft(null);
                    setEditSubject("");
                    setEditBody("");
                    generateDraft();
                  }}
                  className="flex items-center justify-center gap-1.5 font-mono text-[10px] uppercase tracking-wider py-2.5 px-4 rounded-lg border border-border text-text-dim hover:text-text-muted transition-colors cursor-pointer"
                >
                  ↻
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
