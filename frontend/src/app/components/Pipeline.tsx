"use client";

import { useEffect, useRef, useState } from "react";

const STEPS = [
  {
    num: "01",
    title: "Discovery",
    description:
      "AI-powered neural search. Describe your ideal customer in plain English — get matching companies back in seconds.",
    icon: "🔍",
    detail: "Pre-built ICP templates · Semantic matching · Auto-dedup",
  },
  {
    num: "02",
    title: "Crawling",
    description:
      "Automatically visits each company website. Extracts key content, captures visual data. Works on any website, worldwide.",
    icon: "🌐",
    detail: "Parallel scanning · Visual capture · Global coverage",
  },
  {
    num: "03",
    title: "Qualification",
    description:
      "AI reads each website's content and visuals. Scores 0-100 on customer fit. Returns structured signals, red flags, and reasoning.",
    icon: "🧠",
    detail: "Vision + text analysis · Structured output · Pre-filter",
  },
  {
    num: "04",
    title: "Deep Research",
    description:
      "For hot leads (8+), dives deeper across multiple pages. Generates a full sales brief: products, requirements, and pitch angles.",
    icon: "🔬",
    detail: "Multi-page analysis · Sales brief · Talking points",
  },
  {
    num: "05",
    title: "Enrichment",
    description:
      "Finds decision-maker contact details automatically. Emails, phone numbers, and LinkedIn profiles for your top leads.",
    icon: "📇",
    detail: "Contact lookup · Email verification · LinkedIn enrichment",
  },
  {
    num: "06",
    title: "Export",
    description:
      "Results sorted into Hot / Review / Rejected tiers. Export to Excel, CSV, or sync directly to your CRM.",
    icon: "📊",
    detail: "Excel + CSV · CRM integration · Auto-categorized",
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
          <span className="font-mono text-[12px] tracking-[0.3em] text-text-dim">
            {step.num}
          </span>
        </div>

        {/* Title */}
        <h3 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.15em] mb-3">
          {step.title}
        </h3>

        {/* Description */}
        <p className="font-sans text-xs text-text-secondary leading-relaxed mb-4">
          {step.description}
        </p>

        {/* Detail chips */}
        <div className="flex flex-wrap gap-1.5">
          {step.detail.split(" · ").map((chip) => (
            <span
              key={chip}
              className="inline-block font-mono text-[12px] tracking-wider uppercase px-2 py-0.5 rounded border border-border-dim text-text-dim"
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
          <span className="font-mono text-[12px] tracking-[0.5em] uppercase text-secondary/50 block mb-3">
            The Pipeline
          </span>
          <h2 className="font-mono text-2xl md:text-3xl font-bold text-text-primary tracking-tight mb-4">
            Six Steps. Fully Automated.
          </h2>
          <p className="font-sans text-sm text-text-secondary max-w-2xl mx-auto">
            From raw search query to a qualified, enriched sales brief — each
            step runs automatically so you can focus on closing deals.
          </p>
        </div>

        {/* Pipeline Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {STEPS.map((step, i) => (
            <StepCard key={step.num} step={step} index={i} visible={visible} />
          ))}
        </div>

        {/* Output visualization */}
        <div className="mt-16 bg-surface-1 border border-border rounded-xl p-6 md:p-8 max-w-3xl mx-auto">
          <p className="font-mono text-[12px] tracking-[0.3em] uppercase text-secondary/50 mb-4">
            Output
          </p>
          <div className="space-y-3">
            {[
              {
                file: "Hot Leads",
                score: "70-100",
                color: "#ef4444",
                emoji: "🔥",
                action: "Ready for outreach",
              },
              {
                file: "Needs Review",
                score: "40-69",
                color: "#f59e0b",
                emoji: "🔍",
                action: "Human review recommended",
              },
              {
                file: "Not a Fit",
                score: "0-39",
                color: "#71717a",
                emoji: "❌",
                action: "Auto-rejected with reasoning",
              },
            ].map((bucket) => (
              <div
                key={bucket.file}
                className="flex items-center gap-4 bg-surface-2 rounded-lg px-4 py-3 border border-border-dim"
              >
                <span className="text-lg">{bucket.emoji}</span>
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-xs text-text-primary truncate">
                    {bucket.file}
                  </p>
                  <p className="font-mono text-[12px] text-text-dim">
                    {bucket.action}
                  </p>
                </div>
                <span
                  className="font-mono text-[12px] font-bold px-2 py-0.5 rounded"
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
