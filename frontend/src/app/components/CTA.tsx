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
      { threshold: 0.3 },
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref]);
  return visible;
}

export default function CTA() {
  const ref = useRef<HTMLElement>(null);
  const visible = useInView(ref);

  return (
    <section
      id="cta"
      ref={ref}
      className="relative bg-surface-1 border-y border-border-dim py-24 px-6 overflow-hidden"
    >
      {/* Background glow */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full pointer-events-none"
        style={{
          background:
            "radial-gradient(circle, rgba(129,140,248,0.03) 0%, transparent 70%)",
        }}
      />

      <div
        className="relative max-w-3xl mx-auto text-center transition-all duration-700"
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0)" : "translateY(20px)",
        }}
      >
        {/* Badge */}
        <div className="inline-block bg-void border border-secondary/20 rounded-full px-5 py-2 mb-8 font-mono text-[11px]">
          <span className="text-secondary/60">✦</span>{" "}
          <span className="text-text-muted">Free to try · No credit card required</span>
        </div>

        <h2 className="font-mono text-2xl md:text-4xl font-bold text-text-primary tracking-tight mb-4">
          Stop Guessing.
          <br />
          <span className="text-secondary glow-text">Start Hunting.</span>
        </h2>

        <p className="font-sans text-sm text-text-secondary max-w-xl mx-auto mb-8">
          100 leads qualified for under $0.50. Set up in 2 minutes. No
          downloads, no installations — just results. Start your
          free trial today.
        </p>

        {/* Highlights */}
        <div className="flex flex-wrap items-center justify-center gap-6 mb-10 font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim">
          <span>
            Free tier: <span className="text-text-secondary">50 leads/mo</span>
          </span>
          <span className="text-border-bright">|</span>
          <span>
            Setup time: <span className="text-text-secondary">~2 min</span>
          </span>
          <span className="text-border-bright">|</span>
          <span>
            No credit card: <span className="text-secondary">required</span>
          </span>
        </div>

        {/* CTA buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="/signup"
            className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-8 py-4 rounded-lg hover:bg-white/85 transition-colors"
          >
            Start Free Trial
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
          </a>
          <a
            href="#how-it-works"
            className="inline-flex items-center gap-2 border border-secondary/30 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-8 py-4 rounded-lg hover:bg-secondary/10 transition-colors"
          >
            Learn More
          </a>
        </div>
      </div>
    </section>
  );
}
