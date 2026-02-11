"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

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

const PLANS = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    description: "Perfect for trying out the platform and small teams.",
    cta: "Get Started Free",
    ctaHref: "/signup",
    highlight: false,
    features: [
      "50 leads / month",
      "Basic AI qualification",
      "CSV export",
      "3 saved searches",
      "Email support",
      "Community access",
    ],
    limits: [
      "No deep research",
      "No contact enrichment",
    ],
  },
  {
    name: "Pro",
    price: "$49",
    period: "/month",
    description: "For growing sales teams that need more power and volume.",
    cta: "Coming Soon",
    ctaHref: "#",
    highlight: true,
    features: [
      "1,000 leads / month",
      "Advanced AI + vision scoring",
      "Deep research briefs",
      "Contact enrichment",
      "Excel + CRM export",
      "Unlimited saved searches",
      "Priority support",
      "Team collaboration (3 seats)",
    ],
    limits: [],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "Unlimited volume, custom integrations, and dedicated support.",
    cta: "Contact Sales",
    ctaHref: "#",
    highlight: false,
    features: [
      "Unlimited leads",
      "Custom AI models",
      "API access",
      "White-label option",
      "SSO / SAML",
      "Dedicated account manager",
      "Custom integrations",
      "SLA guarantee",
    ],
    limits: [],
  },
];

export default function Pricing() {
  const ref = useRef<HTMLElement>(null);
  const visible = useInView(ref);

  return (
    <section id="pricing" ref={ref} className="bg-surface-1 py-24 px-6 border-y border-border-dim">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] tracking-[0.5em] uppercase text-secondary/50 block mb-3">
            Pricing
          </span>
          <h2 className="font-mono text-2xl md:text-3xl font-bold text-text-primary tracking-tight mb-4">
            Start Free. Scale When Ready.
          </h2>
          <p className="font-sans text-sm text-text-secondary max-w-lg mx-auto">
            No credit card required. Upgrade anytime as your pipeline grows.
          </p>
        </div>

        {/* Plan cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {PLANS.map((plan, i) => (
            <div
              key={plan.name}
              className={`relative rounded-xl p-6 transition-all duration-700 ${
                plan.highlight
                  ? "bg-surface-2 border-2 border-secondary/30 shadow-[0_0_40px_rgba(129,140,248,0.06)]"
                  : "bg-surface-2 border border-border"
              }`}
              style={{
                opacity: visible ? 1 : 0,
                transform: visible ? "translateY(0)" : "translateY(20px)",
                transitionDelay: `${i * 120}ms`,
              }}
            >
              {plan.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="bg-secondary text-void font-mono text-[9px] font-bold uppercase tracking-[0.2em] px-3 py-1 rounded-full">
                    Most Popular
                  </span>
                </div>
              )}

              {/* Plan name */}
              <h3 className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted mb-4">
                {plan.name}
              </h3>

              {/* Price */}
              <div className="flex items-baseline gap-1 mb-2">
                <span className="font-mono text-4xl font-bold text-text-primary">
                  {plan.price}
                </span>
                {plan.period && (
                  <span className="font-mono text-sm text-text-dim">
                    {plan.period}
                  </span>
                )}
              </div>

              <p className="font-sans text-xs text-text-muted leading-relaxed mb-6">
                {plan.description}
              </p>

              {/* CTA */}
              <Link
                href={plan.ctaHref}
                className={`block w-full text-center font-mono text-xs font-bold uppercase tracking-[0.15em] py-3.5 rounded-lg transition-colors mb-6 ${
                  plan.highlight
                    ? "bg-text-primary text-void hover:bg-white/85"
                    : "bg-surface-3 border border-border text-text-secondary hover:border-border-bright hover:text-text-primary"
                }`}
              >
                {plan.cta}
              </Link>

              {/* Features */}
              <ul className="space-y-2.5">
                {plan.features.map((feat) => (
                  <li key={feat} className="flex items-start gap-2.5">
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="text-secondary/60 flex-shrink-0 mt-0.5"
                    >
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    <span className="font-sans text-xs text-text-secondary">
                      {feat}
                    </span>
                  </li>
                ))}
                {plan.limits.map((limit) => (
                  <li key={limit} className="flex items-start gap-2.5">
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="text-text-dim flex-shrink-0 mt-0.5"
                    >
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                    <span className="font-sans text-xs text-text-dim">
                      {limit}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom note */}
        <p className="text-center mt-10 font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim">
          All plans include SSL encryption · GDPR compliant · 99.9% uptime SLA
        </p>
      </div>
    </section>
  );
}
