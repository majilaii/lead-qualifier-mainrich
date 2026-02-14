"use client";

import { useState } from "react";
import { useAuth } from "../../components/auth/SessionProvider";

/* ─── Types ─── */

interface RedditSignal {
  title: string;
  body: string;
  subreddit: string;
  score: number;
  num_comments: number;
  url: string;
  author: string;
  created_date: string;
  age_days: number;
  post_type: string;
  signal_type: string;
  sentiment: string;
  relevance_score: number;
  summary: string;
  key_phrases: string[];
}

interface RedditPulseData {
  query: string;
  subreddits_searched: string[];
  total_posts_found: number;
  signals: RedditSignal[];
  sentiment_breakdown: Record<string, number>;
  top_themes: string[];
  buying_intent_count: number;
  market_summary: string;
  searched_at: string;
}

/* ─── Signal colors ─── */

const SIGNAL_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  buying_intent: { bg: "bg-green-500/15", text: "text-green-400", label: "🔥 Buying Intent" },
  pain_point: { bg: "bg-red-500/15", text: "text-red-400", label: "⚠️ Pain Point" },
  competitor_mention: { bg: "bg-amber-500/15", text: "text-amber-400", label: "👀 Competitor" },
  industry_trend: { bg: "bg-blue-500/15", text: "text-blue-400", label: "📈 Trend" },
  discussion: { bg: "bg-white/5", text: "text-text-muted", label: "💬 Discussion" },
};

const SENTIMENT_COLORS: Record<string, { dot: string; label: string }> = {
  positive: { dot: "bg-green-400", label: "Positive" },
  negative: { dot: "bg-red-400", label: "Negative" },
  neutral: { dot: "bg-gray-400", label: "Neutral" },
  frustrated: { dot: "bg-orange-400", label: "Frustrated" },
};

const TIME_RANGES = [
  { value: "day", label: "24h" },
  { value: "week", label: "7d" },
  { value: "month", label: "30d" },
  { value: "year", label: "1y" },
];

/* ─── Page ─── */

export default function RedditPulsePage() {
  const { session } = useAuth();
  const [industry, setIndustry] = useState("");
  const [technology, setTechnology] = useState("");
  const [customQuery, setCustomQuery] = useState("");
  const [timeRange, setTimeRange] = useState("month");
  const [loading, setLoading] = useState(false);
  const [pulse, setPulse] = useState<RedditPulseData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const handleSearch = async () => {
    if (!industry && !technology && !customQuery) return;
    if (!session?.access_token) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/proxy/reddit/pulse", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          industry: industry || undefined,
          technology: technology || undefined,
          custom_query: customQuery || undefined,
          time_range: timeRange,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to fetch Reddit signals");
      }

      const data: RedditPulseData = await res.json();
      setPulse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const filteredSignals =
    pulse?.signals.filter((s) => filter === "all" || s.signal_type === filter) ?? [];

  const totalSentiment = pulse
    ? Object.values(pulse.sentiment_breakdown).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">
          Reddit Pulse
        </h1>
        <p className="font-sans text-sm text-text-muted mt-1">
          Market sentiment & buying intent signals from Reddit — what the market is really thinking
        </p>
      </div>

      {/* Search Form */}
      <div className="bg-surface-2 border border-border rounded-xl p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-1.5">
              Industry
            </label>
            <input
              type="text"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              placeholder="e.g. robotics, SaaS, manufacturing"
              className="w-full bg-surface-3 border border-border-dim rounded-lg px-3 py-2.5 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/50 transition-colors"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-1.5">
              Technology / Product
            </label>
            <input
              type="text"
              value={technology}
              onChange={(e) => setTechnology(e.target.value)}
              placeholder="e.g. CRM, brushless motors, AI tools"
              className="w-full bg-surface-3 border border-border-dim rounded-lg px-3 py-2.5 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/50 transition-colors"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-1.5">
              Custom Search
            </label>
            <input
              type="text"
              value={customQuery}
              onChange={(e) => setCustomQuery(e.target.value)}
              placeholder="e.g. looking for magnet supplier"
              className="w-full bg-surface-3 border border-border-dim rounded-lg px-3 py-2.5 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/50 transition-colors"
            />
          </div>
        </div>

        <div className="flex items-center justify-between">
          {/* Time range selector */}
          <div className="flex items-center gap-1">
            {TIME_RANGES.map((t) => (
              <button
                key={t.value}
                onClick={() => setTimeRange(t.value)}
                className={`font-mono text-[10px] uppercase tracking-[0.15em] px-3 py-1.5 rounded-md transition-colors cursor-pointer ${
                  timeRange === t.value
                    ? "bg-secondary/15 text-secondary border border-secondary/30"
                    : "text-text-dim hover:text-text-muted border border-transparent"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <button
            onClick={handleSearch}
            disabled={loading || (!industry && !technology && !customQuery)}
            className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-[10px] font-bold uppercase tracking-[0.15em] px-6 py-2.5 rounded-lg hover:bg-white/85 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            {loading ? (
              <>
                <div className="w-3 h-3 border-2 border-void/30 border-t-void rounded-full animate-spin" />
                Scanning Reddit...
              </>
            ) : (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                Get Pulse
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4">
          <p className="font-mono text-xs text-red-400">{error}</p>
        </div>
      )}

      {/* Results */}
      {pulse && (
        <>
          {/* Market Summary */}
          <div className="bg-surface-2 border border-secondary/20 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-secondary text-sm">◈</span>
              <h2 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.1em]">
                Market Pulse
              </h2>
            </div>
            <p className="font-sans text-sm text-text-secondary leading-relaxed">
              {pulse.market_summary}
            </p>
          </div>

          {/* Stats Row */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-surface-2 border border-border rounded-xl p-4">
              <span className="font-mono text-2xl font-bold text-text-primary">
                {pulse.total_posts_found}
              </span>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mt-2">
                Posts Found
              </p>
            </div>
            <div className="bg-surface-2 border border-green-500/20 rounded-xl p-4">
              <span className="font-mono text-2xl font-bold text-green-400">
                {pulse.buying_intent_count}
              </span>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mt-2">
                Buying Intent
              </p>
            </div>
            <div className="bg-surface-2 border border-border rounded-xl p-4">
              <span className="font-mono text-2xl font-bold text-text-primary">
                {pulse.subreddits_searched.length}
              </span>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mt-2">
                Subreddits
              </p>
            </div>

            {/* Sentiment bar */}
            <div className="bg-surface-2 border border-border rounded-xl p-4 col-span-2">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mb-2">
                Sentiment
              </p>
              <div className="flex h-4 rounded-md overflow-hidden bg-surface-3 mb-2">
                {totalSentiment > 0 &&
                  Object.entries(pulse.sentiment_breakdown)
                    .filter(([, v]) => v > 0)
                    .map(([key, val]) => {
                      const pct = (val / totalSentiment) * 100;
                      const color = SENTIMENT_COLORS[key]?.dot ?? "bg-gray-500";
                      return (
                        <div
                          key={key}
                          className={`${color} transition-all`}
                          style={{ width: `${pct}%` }}
                          title={`${SENTIMENT_COLORS[key]?.label}: ${val}`}
                        />
                      );
                    })}
              </div>
              <div className="flex flex-wrap gap-3">
                {Object.entries(pulse.sentiment_breakdown).map(([key, val]) => (
                  <div key={key} className="flex items-center gap-1">
                    <span className={`w-2 h-2 rounded-full ${SENTIMENT_COLORS[key]?.dot ?? "bg-gray-500"}`} />
                    <span className="font-mono text-[9px] text-text-dim">
                      {SENTIMENT_COLORS[key]?.label}: {val}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Top Themes */}
          {pulse.top_themes.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted self-center mr-1">
                Themes:
              </span>
              {pulse.top_themes.map((theme) => (
                <span
                  key={theme}
                  className="bg-secondary/10 border border-secondary/20 text-secondary font-mono text-[10px] px-2.5 py-1 rounded-md"
                >
                  {theme}
                </span>
              ))}
            </div>
          )}

          {/* Signal Type Filter */}
          <div className="flex items-center gap-2 border-b border-border-dim pb-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mr-1">
              Filter:
            </span>
            <button
              onClick={() => setFilter("all")}
              className={`font-mono text-[10px] px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                filter === "all"
                  ? "bg-white/10 text-text-primary"
                  : "text-text-dim hover:text-text-muted"
              }`}
            >
              All ({pulse.signals.length})
            </button>
            {Object.entries(SIGNAL_COLORS).map(([key, val]) => {
              const count = pulse.signals.filter((s) => s.signal_type === key).length;
              if (count === 0) return null;
              return (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  className={`font-mono text-[10px] px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                    filter === key
                      ? `${val.bg} ${val.text}`
                      : "text-text-dim hover:text-text-muted"
                  }`}
                >
                  {val.label} ({count})
                </button>
              );
            })}
          </div>

          {/* Signals List */}
          <div className="space-y-3">
            {filteredSignals.length === 0 ? (
              <div className="text-center py-12">
                <p className="font-mono text-xs text-text-dim">
                  No signals match this filter.
                </p>
              </div>
            ) : (
              filteredSignals.map((signal, idx) => {
                const signalStyle = SIGNAL_COLORS[signal.signal_type] ?? SIGNAL_COLORS.discussion;
                const sentimentStyle = SENTIMENT_COLORS[signal.sentiment] ?? SENTIMENT_COLORS.neutral;
                return (
                  <a
                    key={idx}
                    href={signal.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block bg-surface-2 border border-border rounded-xl p-4 hover:border-secondary/30 transition-colors group"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        {/* Header row */}
                        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                          <span className={`${signalStyle.bg} ${signalStyle.text} font-mono text-[9px] uppercase tracking-[0.1em] px-2 py-0.5 rounded`}>
                            {signalStyle.label}
                          </span>
                          <span className="flex items-center gap-1">
                            <span className={`w-1.5 h-1.5 rounded-full ${sentimentStyle.dot}`} />
                            <span className="font-mono text-[9px] text-text-dim">
                              {sentimentStyle.label}
                            </span>
                          </span>
                          <span className="font-mono text-[9px] text-secondary/60">
                            {signal.subreddit}
                          </span>
                          <span className="font-mono text-[9px] text-text-dim">
                            {signal.age_days}d ago
                          </span>
                        </div>

                        {/* Title */}
                        {signal.title && (
                          <p className="font-mono text-xs text-text-primary mb-1 group-hover:text-secondary transition-colors">
                            {signal.title}
                          </p>
                        )}

                        {/* Summary */}
                        <p className="font-sans text-[11px] text-text-muted leading-relaxed">
                          {signal.summary || signal.body.slice(0, 200)}
                        </p>

                        {/* Key phrases */}
                        {signal.key_phrases.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {signal.key_phrases.map((phrase) => (
                              <span
                                key={phrase}
                                className="bg-surface-3 text-text-dim font-mono text-[9px] px-1.5 py-0.5 rounded"
                              >
                                {phrase}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Right side: engagement stats */}
                      <div className="flex flex-col items-end gap-1 flex-shrink-0">
                        <span className="font-mono text-xs text-text-primary">
                          ↑{signal.score}
                        </span>
                        <span className="font-mono text-[9px] text-text-dim">
                          {signal.num_comments} comments
                        </span>
                        <div
                          className="w-12 h-1.5 rounded-full bg-surface-3 mt-1"
                          title={`Relevance: ${Math.round(signal.relevance_score * 100)}%`}
                        >
                          <div
                            className="h-full rounded-full bg-secondary/60"
                            style={{ width: `${signal.relevance_score * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </a>
                );
              })
            )}
          </div>
        </>
      )}

      {/* Empty state */}
      {!pulse && !loading && !error && (
        <div className="text-center py-16 bg-surface-2 border border-border rounded-xl">
          <div className="text-4xl mb-4">📡</div>
          <h3 className="font-mono text-sm text-text-primary mb-2">
            Tap into the Reddit Pulse
          </h3>
          <p className="font-sans text-xs text-text-muted max-w-md mx-auto">
            Search for your industry or technology to discover what real people are saying —
            buying intent signals, pain points, competitor mentions, and market sentiment from
            thousands of Reddit discussions.
          </p>
          <p className="font-mono text-[10px] text-text-dim mt-4">
            Free • No Reddit account needed • Powered by PullPush + Reddit API
          </p>
        </div>
      )}
    </div>
  );
}
