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
      "Our AI doesn't just read text — it sees the website. Product pages, factory photos, and technical diagrams all influence the score.",
    tag: "AI-Powered",
  },
  {
    title: "Multi-Model Intelligence",
    description:
      "Multiple AI models work in tandem with automatic failover. If one model is unavailable, the next picks up. Qualification never stops.",
    tag: "Fault-Tolerant",
  },
  {
    title: "Pennies Per Lead",
    description:
      "Process 100 leads for under $0.50. Vision analysis, deep research, and structured results all included. Enterprise power, startup pricing.",
    tag: "Cost-Efficient",
  },
  {
    title: "Auto-Save & Resume",
    description:
      "Progress is saved after every lead. Connection lost, browser closed, or session expired — pick up exactly where you left off.",
    tag: "Resilient",
  },
  {
    title: "Structured Reports",
    description:
      "Every lead gets a detailed report: confidence score, company type, industry category, key signals, red flags, and reasoning.",
    tag: "Actionable",
  },
  {
    title: "Smart Pre-Filter",
    description:
      "Obvious non-fits (consultancies, agencies, pure software) are rejected instantly — saving you time and credits on real prospects only.",
    tag: "Efficient",
  },
  {
    title: "Parallel Processing",
    description:
      "Process multiple leads simultaneously. Qualify 5 companies at once with configurable concurrency for maximum throughput.",
    tag: "Fast",
  },
  {
    title: "Deep Sales Briefs",
    description:
      "For hot leads: products they make, key requirements, decision-maker titles, suggested pitch angle, and talking points.",
    tag: "Sales-Ready",
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
