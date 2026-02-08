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
      title: "Feed It Leads",
      description:
        "Drop a CSV from LinkedIn Sales Navigator, or let Exa AI discover companies matching your ideal customer profile automatically.",
      code: "python test_exa.py --export",
    },
    {
      num: "02",
      title: "Watch It Hunt",
      description:
        "The pipeline crawls websites, reads them with AI vision, scores each company 1-10, and sorts results into Hot, Review, and Rejected buckets.",
      code: "python main.py --input leads.csv --deep-research",
    },
    {
      num: "03",
      title: "Close the Deal",
      description:
        "Get a ready-to-use sales brief for every hot lead: what they build, who to call, and exactly what to say. Export to Excel or Google Sheets.",
      code: "python export.py excel",
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

              {/* Code */}
              <div className="bg-void border border-border-dim rounded-md px-3 py-2 font-mono text-[11px]">
                <span className="text-text-dim">$ </span>
                <span className="text-secondary/70">{step.code}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
