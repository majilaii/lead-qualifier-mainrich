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
      { threshold: 0.2 }
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref]);
  return visible;
}

export default function HowItWorks() {
  const ref = useRef<HTMLElement>(null);
  const visible = useInView(ref);

  const steps = [
    {
      num: "01",
      title: "Describe Your Ideal Customer",
      description:
        "Upload a CSV of prospects or simply describe your ideal customer in plain English. Our AI instantly understands your target market.",
      detail: "CSV upload · Natural language · ICP builder",
    },
    {
      num: "02",
      title: "AI Finds & Qualifies",
      description:
        "Our engine scans the web, analyzes company websites with AI vision, scores each prospect 1-10, and sorts them into Hot, Review, and Rejected.",
      detail: "Web scanning · AI scoring · Auto-categorization",
    },
    {
      num: "03",
      title: "Close the Deal",
      description:
        "Get a ready-to-use sales brief for every hot lead: what they build, who to contact, and exactly what to say. Export or sync to your CRM.",
      detail: "Sales briefs · Excel export · CRM sync",
    },
  ];

  return (
    <section
      id="how-it-works"
      ref={ref}
      className="bg-surface-1 py-24 px-6 border-y border-border-dim"
    >
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] tracking-[0.5em] uppercase text-secondary/50 block mb-3">
            How It Works
          </span>
          <h2 className="font-mono text-2xl md:text-3xl font-bold text-text-primary tracking-tight mb-4">
            Three Steps. Zero Busywork.
          </h2>
          <p className="font-sans text-sm text-text-secondary max-w-lg mx-auto">
            From a list of names to qualified, research-backed sales targets — in
            minutes, not weeks.
          </p>
        </div>

        {/* Steps */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {steps.map((step, i) => (
            <div
              key={step.num}
              className="relative transition-all duration-700"
              style={{
                opacity: visible ? 1 : 0,
                transform: visible ? "translateY(0)" : "translateY(20px)",
                transitionDelay: `${i * 150}ms`,
              }}
            >
              {/* Number */}
              <div className="flex items-center gap-3 mb-5">
                <span className="font-mono text-4xl font-bold text-text-dim">
                  {step.num}
                </span>
                {i < steps.length - 1 && (
                  <div className="hidden md:block flex-1 h-px bg-gradient-to-r from-border-bright to-transparent" />
                )}
              </div>

              {/* Content */}
              <h3 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.12em] mb-3">
                {step.title}
              </h3>
              <p className="font-sans text-xs text-text-secondary leading-relaxed mb-4">
                {step.description}
              </p>

              {/* Detail */}
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
          ))}
        </div>
      </div>
    </section>
  );
}
