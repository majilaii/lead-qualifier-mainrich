import Link from "next/link";

const TRUST_MARKERS = [
  "Built for technical B2B sales teams",
  "CRM-ready lead exports",
  "No setup call required",
];

const METRICS = [
  { label: "Avg. Time To First Qualified Lead", value: "9 min" },
  { label: "Manual Research Reduced", value: "73%" },
  { label: "Lead Scoring Precision", value: "94%" },
];

const SAMPLE_LEADS = [
  {
    company: "Nova Industrial Systems",
    score: 96,
    tier: "Hot",
    signal: "Hiring controls engineers in Dallas",
  },
  {
    company: "Helix Motion Labs",
    score: 89,
    tier: "Review",
    signal: "New Series B, expanding GTM in US",
  },
  {
    company: "Orion Assembly Tech",
    score: 82,
    tier: "Review",
    signal: "Announced robotics integration roadmap",
  },
];

export default function HeroSection() {
  return (
    <section className="relative overflow-hidden bg-void px-6 pb-20 pt-28 md:pb-24 md:pt-36">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(70% 55% at 78% 18%, rgba(129,140,248,0.14), transparent 60%), radial-gradient(55% 45% at 20% 14%, rgba(255,255,255,0.08), transparent 62%)",
        }}
      />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_bottom,rgba(255,255,255,0.06)_1px,transparent_1px),linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:42px_42px] opacity-25" />

      <div className="relative mx-auto grid w-full max-w-7xl items-start gap-14 lg:grid-cols-[1.06fr_0.94fr]">
        <div className="stagger-children">
          <p className="mb-5 inline-flex items-center gap-3 rounded-full border border-border bg-surface-1/80 px-4 py-2 font-mono text-[12px] uppercase tracking-[0.22em] text-text-secondary">
            Revenue Teams At Modern B2B Companies
          </p>

          <h1 className="max-w-3xl font-sans text-4xl font-semibold leading-tight text-text-primary md:text-6xl">
            Find the right B2B accounts before your competitors do.
          </h1>

          <p className="mt-6 max-w-2xl font-sans text-xs leading-relaxed text-text-secondary md:text-lg">
            Hunt turns your ideal customer profile into a live prospecting engine
            that discovers, scores, and enriches high-intent companies in one
            workflow.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 rounded bg-text-primary px-6 py-3 font-mono text-xs font-semibold uppercase tracking-[0.18em] text-void transition-colors hover:bg-white/85"
            >
              Start Free
              <span className="text-[12px]">&#x2192;</span>
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center rounded border border-border-bright bg-surface-1/70 px-6 py-3 font-mono text-xs font-semibold uppercase tracking-[0.18em] text-text-primary transition-colors hover:bg-surface-2"
            >
              View Product
            </Link>
          </div>

          <div className="mt-10 flex flex-wrap gap-3">
            {TRUST_MARKERS.map((marker) => (
              <span
                key={marker}
                className="rounded border border-border bg-surface-1/70 px-3 py-2 font-mono text-[12px] uppercase tracking-[0.18em] text-text-muted"
              >
                {marker}
              </span>
            ))}
          </div>

          <div className="mt-11 grid gap-4 sm:grid-cols-3">
            {METRICS.map((metric) => (
              <div
                key={metric.label}
                className="rounded border border-border bg-surface-1/70 p-4"
              >
                <p className="font-mono text-2xl font-semibold text-text-primary">
                  {metric.value}
                </p>
                <p className="mt-2 font-mono text-[12px] uppercase tracking-[0.18em] text-text-muted">
                  {metric.label}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="animate-slide-up rounded-2xl border border-border bg-surface-1/90 p-5 shadow-[0_18px_80px_rgba(0,0,0,0.5)] backdrop-blur">
          <div className="rounded-xl border border-border-dim bg-void p-4">
            <div className="mb-5 flex items-center justify-between border-b border-border-dim pb-3">
              <div>
                <p className="font-mono text-[12px] uppercase tracking-[0.2em] text-text-muted">
                  Live Pipeline Preview
                </p>
                <p className="mt-1 font-mono text-sm text-text-primary">
                  Q1 Automation Prospecting
                </p>
              </div>
              <span className="rounded-full border border-secondary/35 bg-secondary/10 px-3 py-1 font-mono text-[12px] uppercase tracking-[0.16em] text-secondary">
                Running
              </span>
            </div>

            <div className="mb-4 grid gap-2 rounded border border-border-dim bg-surface-1/40 p-3 font-mono text-[12px] uppercase tracking-[0.14em] text-text-muted sm:grid-cols-3">
              <p className="border-border-dim sm:border-r sm:pr-2">
                Searched
                <span className="mt-1 block text-sm text-text-primary">312</span>
              </p>
              <p className="border-border-dim sm:border-r sm:px-2">
                Qualified
                <span className="mt-1 block text-sm text-text-primary">24</span>
              </p>
              <p className="sm:pl-2">
                Hot Tier
                <span className="mt-1 block text-sm text-text-primary">7</span>
              </p>
            </div>

            <div className="space-y-2">
              {SAMPLE_LEADS.map((lead) => (
                <div
                  key={lead.company}
                  className="rounded border border-border-dim bg-surface-1/50 p-3"
                >
                  <div className="flex items-center justify-between gap-4">
                    <p className="font-sans text-sm text-text-primary">
                      {lead.company}
                    </p>
                    <span className="font-mono text-xs text-text-secondary">
                      {lead.score}/100
                    </span>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-4">
                    <span
                      className={`rounded px-2 py-1 font-mono text-[12px] uppercase tracking-[0.14em] ${
                        lead.tier === "Hot"
                          ? "bg-hot/15 text-hot"
                          : "bg-review/15 text-review"
                      }`}
                    >
                      {lead.tier}
                    </span>
                    <p className="font-sans text-xs text-text-muted">
                      {lead.signal}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
