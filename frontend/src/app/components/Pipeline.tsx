"use client";

import { useEffect, useRef, useState } from "react";

const STEPS = [
  {
    num: "01",
    title: "Discovery",
    module: "test_exa.py",
    description:
      "Neural search powered by Exa AI. Describe your ideal customer in plain English — get matching companies back in seconds.",
    icon: "🔍",
    detail: "12 pre-built ICP queries · Semantic matching · Auto-dedup",
  },
  {
    num: "02",
    title: "Crawling",
    module: "scraper.py",
    description:
      "Headless Chromium visits each website. Extracts clean markdown text + captures screenshots. Auto-removes popups and cookie banners.",
    icon: "🌐",
    detail: "Parallel crawling · Screenshot capture · Bot-detection bypass",
  },
  {
    num: "03",
    title: "Qualification",
    module: "intelligence.py",
    description:
      "The LLM reads the website content + screenshot. Scores 1-10 on customer fit. Returns structured signals, red flags, and reasoning.",
    icon: "🧠",
    detail: "Vision + text analysis · Structured JSON output · Pre-filter",
  },
  {
    num: "04",
    title: "Deep Research",
    module: "deep_research.py",
    description:
      "For hot leads (8+), crawls up to 5 pages. Generates a sales brief: products, motor types, magnet requirements, and pitch angles.",
    icon: "🔬",
    detail: "Multi-page crawl · Sales brief · Talking points generator",
  },
  {
    num: "05",
    title: "Enrichment",
    module: "enrichment.py",
    description:
      "Looks up decision-maker emails and phone numbers via Apollo.io or Hunter.io. Manual mode available at zero cost.",
    icon: "📇",
    detail: "Apollo + Hunter integration · Manual fallback · Rate-limited",
  },
  {
    num: "06",
    title: "Export",
    module: "export.py",
    description:
      "Results sorted into Hot / Review / Rejected buckets. Export to Excel with color-coded sheets or sync live to Google Sheets.",
    icon: "📊",
    detail: "Excel + Google Sheets · Watch mode · Auto-categorized",
  },
];

function useInView(ref: React.RefObject<HTMLElement | null>) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true);
      },
      { threshold: 0.15 }
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref]);
  return visible;
}

function StepCard({
  step,
  index,
  visible,
}: {
  step: (typeof STEPS)[0];
  index: number;
  visible: boolean;
}) {
  return (
    <div
      className="relative group transition-all duration-700"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(24px)",
        transitionDelay: `${index * 100}ms`,
      }}
    >
      <div className="relative bg-surface-2 border border-border rounded-lg p-6 hover:border-secondary/20 hover:bg-surface-3 transition-all duration-300 h-full">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <span className="text-3xl">{step.icon}</span>
          <span className="font-mono text-[10px] tracking-[0.3em] text-text-dim">
            {step.num}
          </span>
        </div>

        {/* Title + Module */}
        <h3 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.15em] mb-1">
          {step.title}
        </h3>
        <p className="font-mono text-[10px] text-secondary/40 mb-3">
          {step.module}
        </p>

        {/* Description */}
        <p className="font-sans text-xs text-text-secondary leading-relaxed mb-4">
          {step.description}
        </p>

        {/* Detail chips */}
        <div className="flex flex-wrap gap-1.5">
          {step.detail.split(" · ").map((chip) => (
            <span
              key={chip}
              className="inline-block font-mono text-[9px] tracking-wider uppercase px-2 py-0.5 rounded border border-border-dim text-text-dim"
            >
              {chip}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Pipeline() {
  const ref = useRef<HTMLElement>(null);
  const visible = useInView(ref);

  return (
    <section id="pipeline" ref={ref} className="bg-void py-24 px-6">
      <div className="max-w-7xl mx-auto">
        {/* Section Header */}
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] tracking-[0.5em] uppercase text-secondary/50 block mb-3">
            The Pipeline
          </span>
          <h2 className="font-mono text-2xl md:text-3xl font-bold text-text-primary tracking-tight mb-4">
            Six Modules. One Command.
          </h2>
          <p className="font-sans text-sm text-text-secondary max-w-2xl mx-auto">
            From raw search query to a qualified, enriched sales brief — each
            step is a standalone Python module that can be run independently or
            as a full pipeline.
          </p>

          {/* Code snippet */}
          <div className="inline-block mt-6 bg-surface-2 border border-border rounded-lg px-5 py-3 font-mono text-xs text-text-secondary">
            <span className="text-text-dim">$</span>{" "}
            <span className="text-secondary/70">python main.py</span>{" "}
            <span className="text-text-muted">
              --input leads.csv --deep-research
            </span>
          </div>
        </div>

        {/* Pipeline Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {STEPS.map((step, i) => (
            <StepCard key={step.num} step={step} index={i} visible={visible} />
          ))}
        </div>

        {/* Output visualization */}
        <div className="mt-16 bg-surface-1 border border-border rounded-xl p-6 md:p-8 max-w-3xl mx-auto">
          <p className="font-mono text-[10px] tracking-[0.3em] uppercase text-secondary/50 mb-4">
            Output
          </p>
          <div className="space-y-3">
            {[
              {
                file: "qualified_hot_leads.csv",
                score: "8-10",
                color: "#ef4444",
                emoji: "🔥",
                action: "Ready for outreach",
              },
              {
                file: "review_manual_check.csv",
                score: "4-7",
                color: "#f59e0b",
                emoji: "🔍",
                action: "Human review needed",
              },
              {
                file: "rejected_with_reasons.csv",
                score: "1-3",
                color: "#71717a",
                emoji: "❌",
                action: "Not a fit (with reasoning)",
              },
            ].map((bucket) => (
              <div
                key={bucket.file}
                className="flex items-center gap-4 bg-surface-2 rounded-lg px-4 py-3 border border-border-dim"
              >
                <span className="text-lg">{bucket.emoji}</span>
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-xs text-text-primary truncate">
                    output/{bucket.file}
                  </p>
                  <p className="font-mono text-[10px] text-text-dim">
                    {bucket.action}
                  </p>
                </div>
                <span
                  className="font-mono text-[10px] font-bold px-2 py-0.5 rounded"
                  style={{
                    color: bucket.color,
                    border: `1px solid ${bucket.color}33`,
                  }}
                >
                  {bucket.score}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
