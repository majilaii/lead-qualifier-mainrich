"use client";

import { useEffect, useRef, useState } from "react";

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

const FEATURES = [
  {
    title: "Vision + Text AI",
    description:
      "The LLM doesn't just read text — it sees the screenshot. Product pages, factory photos, and technical diagrams all influence the score.",
    tag: "intelligence.py",
  },
  {
    title: "Multi-Model Fallback",
    description:
      "Kimi K2.5 → GPT-4o → GPT-4o-mini → Keyword matching. If one model fails, the next picks up. Qualification never stops.",
    tag: "Fault-tolerant",
  },
  {
    title: "$0.002 Per Lead",
    description:
      "Process 100 leads for under $0.50 with Kimi. Vision analysis, deep research, and structured JSON output included.",
    tag: "Cost-efficient",
  },
  {
    title: "Checkpoint & Resume",
    description:
      "Pipeline saves progress after every lead. Crash, Ctrl+C, or close your laptop — pick up exactly where you left off.",
    tag: "Resilient",
  },
  {
    title: "Structured Output",
    description:
      "Every lead gets a JSON result: confidence_score, hardware_type, industry_category, key_signals, red_flags, and reasoning.",
    tag: "Actionable",
  },
  {
    title: "Pre-Filter Engine",
    description:
      "Obvious non-fits (SaaS, agencies, consultancies) are rejected instantly without burning any LLM tokens. Smart cost savings.",
    tag: "Efficient",
  },
  {
    title: "Parallel Crawling",
    description:
      "One shared Chromium instance, multiple concurrent pages. Process 5 leads simultaneously with configurable concurrency limits.",
    tag: "Fast",
  },
  {
    title: "Deep Sales Briefs",
    description:
      "For hot leads: products they make, motor types, magnet requirements, decision-maker titles, suggested pitch angle, and talking points.",
    tag: "deep_research.py",
  },
];

export default function Features() {
  const ref = useRef<HTMLElement>(null);
  const visible = useInView(ref);

  return (
    <section id="features" ref={ref} className="bg-void py-24 px-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] tracking-[0.5em] uppercase text-secondary/50 block mb-3">
            Features
          </span>
          <h2 className="font-mono text-2xl md:text-3xl font-bold text-text-primary tracking-tight mb-4">
            Built for Precision
          </h2>
          <p className="font-sans text-sm text-text-secondary max-w-lg mx-auto">
            Every feature is designed for one thing: finding the companies that
            actually need what you sell.
          </p>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {FEATURES.map((feat, i) => (
            <div
              key={feat.title}
              className="bg-surface-2 border border-border rounded-lg p-5 hover:border-secondary/20 transition-all duration-300 group"
              style={{
                opacity: visible ? 1 : 0,
                transform: visible ? "translateY(0)" : "translateY(16px)",
                transitionDelay: `${i * 60}ms`,
                transitionDuration: "600ms",
              }}
            >
              {/* Tag */}
              <span className="inline-block font-mono text-[9px] tracking-[0.2em] uppercase text-secondary/35 border border-secondary/10 rounded px-1.5 py-0.5 mb-3 group-hover:text-secondary/60 group-hover:border-secondary/25 transition-colors">
                {feat.tag}
              </span>

              {/* Title */}
              <h3 className="font-mono text-xs font-semibold text-text-primary uppercase tracking-[0.1em] mb-2">
                {feat.title}
              </h3>

              {/* Description */}
              <p className="font-sans text-[11px] text-text-muted leading-relaxed">
                {feat.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
