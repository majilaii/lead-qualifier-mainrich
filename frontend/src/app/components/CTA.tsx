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
        {/* Terminal prompt */}
        <div className="inline-block bg-void border border-border rounded-lg px-5 py-3 mb-8 font-mono text-xs">
          <span className="text-text-dim">$ </span>
          <span className="text-secondary/70">git clone</span>{" "}
          <span className="text-text-muted">
            https://github.com/mainrich/lead-qualifier.git
          </span>
          <span className="inline-block w-[2px] h-3 bg-text-primary/50 ml-1 align-middle animate-blink" />
        </div>

        <h2 className="font-mono text-2xl md:text-4xl font-bold text-text-primary tracking-tight mb-4">
          Stop Guessing.
          <br />
          <span className="text-secondary glow-text">Start Hunting.</span>
        </h2>

        <p className="font-sans text-sm text-text-secondary max-w-xl mx-auto mb-8">
          100 leads qualified for under $0.50. Set up in 5 minutes. Run it from
          the terminal. No SaaS subscriptions, no dashboards, no fluff — just
          results.
        </p>

        {/* Cost breakdown */}
        <div className="flex flex-wrap items-center justify-center gap-6 mb-10 font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim">
          <span>
            Exa Discovery: <span className="text-text-secondary">~$0.06</span>
          </span>
          <span className="text-border-bright">|</span>
          <span>
            100 Leads: <span className="text-text-secondary">~$0.20</span>
          </span>
          <span className="text-border-bright">|</span>
          <span>
            Deep Research:{" "}
            <span className="text-text-secondary">~$0.005/lead</span>
          </span>
        </div>

        {/* CTA buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="https://github.com/majilaii/lead-qualifier-mainrich"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-8 py-4 rounded-lg hover:bg-white/85 transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
            </svg>
            View on GitHub
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
