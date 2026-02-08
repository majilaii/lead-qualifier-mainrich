"use client";

import { useEffect, useRef, useState } from "react";

const STATS = [
  { value: "7.2B", label: "Data Points Scanned" },
  { value: "<500ms", label: "Avg. Qualification Time" },
  { value: "94%", label: "Accuracy Rate" },
  { value: "$0.002", label: "Cost Per Lead" },
];

function useInView(ref: React.RefObject<HTMLElement | null>) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true);
      },
      { threshold: 0.3 }
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref]);
  return visible;
}

export default function StatsBar() {
  const ref = useRef<HTMLDivElement>(null);
  const visible = useInView(ref);

  return (
    <section
      ref={ref}
      className="relative bg-surface-1 border-y border-border-dim py-16 px-6"
    >
      <div className="max-w-6xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
        {STATS.map((stat, i) => (
          <div
            key={stat.label}
            className="text-center transition-all duration-700"
            style={{
              opacity: visible ? 1 : 0,
              transform: visible ? "translateY(0)" : "translateY(16px)",
              transitionDelay: `${i * 120}ms`,
            }}
          >
            <p className="font-mono text-3xl md:text-4xl font-bold text-text-primary glow-text mb-2">
              {stat.value}
            </p>
            <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
              {stat.label}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
