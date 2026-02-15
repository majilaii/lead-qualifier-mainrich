"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "./auth/SessionProvider";

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
    id: "free",
    price: "$0",
    period: "forever",
    description: "Perfect for trying out the platform.",
    highlight: false,
    features: [
      "3 hunts / month",
      "25 leads per hunt",
      "10 contact enrichments",
      "Basic AI qualification",
      "CSV export",
      "Email support",
    ],
    limits: [
      "No deep research",
    ],
  },
  {
    name: "Pro",
    id: "pro",
    price: "$49",
    period: "/month",
    description: "For growing sales teams that need more power and volume.",
    highlight: true,
    features: [
      "20 hunts / month",
      "100 leads per hunt",
      "200 contact enrichments",
      "Deep research briefs",
      "Priority support",
      "Unlimited saved searches",
    ],
    limits: [],
  },
  {
    name: "Enterprise",
    id: "enterprise",
    price: "$199",
    period: "/month",
    description: "Unlimited volume, priority everything, and dedicated support.",
    highlight: false,
    features: [
      "Unlimited hunts",
      "500 leads per hunt",
      "1,000 contact enrichments",
      "Deep research + priority",
      "API access",
      "Dedicated account manager",
    ],
    limits: [],
  },
];

export default function Pricing() {
  const ref = useRef<HTMLElement>(null);
  const visible = useInView(ref);
  const { user, session } = useAuth();
  const [checkingOut, setCheckingOut] = useState<string | null>(null);

  const handleCheckout = async (planId: string) => {
    if (planId === "free") return;
    if (!user || !session?.access_token) {
      // Redirect to signup first
      window.location.href = "/signup";
      return;
    }

    setCheckingOut(planId);
    try {
      const resp = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ plan: planId }),
      });
      const data = await resp.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (e) {
      console.error("Checkout error:", e);
    } finally {
      setCheckingOut(null);
    }
  };

  const getCtaText = (planId: string) => {
    if (checkingOut === planId) return "Redirecting…";
    if (planId === "free") return user ? "Current Plan" : "Get Started Free";
    return `Upgrade to ${planId.charAt(0).toUpperCase() + planId.slice(1)}`;
  };

  const getCtaHref = (planId: string) => {
    if (planId === "free") return user ? "/dashboard" : "/signup";
    return "#";
  };

  return (
    <section id="pricing" ref={ref} className="bg-surface-1 py-24 px-6 border-y border-border-dim">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16">
          <span className="font-mono text-[12px] tracking-[0.5em] uppercase text-secondary/50 block mb-3">
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
                  <span className="bg-secondary text-void font-mono text-[14px] font-bold uppercase tracking-[0.2em] px-3 py-1 rounded-full">
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
              {plan.id === "free" ? (
                <Link
                  href={getCtaHref(plan.id)}
                  className="block w-full text-center font-mono text-xs font-bold uppercase tracking-[0.15em] py-3.5 rounded-lg transition-colors mb-6 bg-surface-3 border border-border text-text-secondary hover:border-border-bright hover:text-text-primary"
                >
                  {getCtaText(plan.id)}
                </Link>
              ) : (
                <button
                  onClick={() => handleCheckout(plan.id)}
                  disabled={checkingOut === plan.id}
                  className={`block w-full text-center font-mono text-xs font-bold uppercase tracking-[0.15em] py-3.5 rounded-lg transition-colors mb-6 cursor-pointer ${
                    plan.highlight
                      ? "bg-text-primary text-void hover:bg-white/85"
                      : "bg-surface-3 border border-border text-text-secondary hover:border-border-bright hover:text-text-primary"
                  } disabled:opacity-50`}
                >
                  {getCtaText(plan.id)}
                </button>
              )}

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
        <p className="text-center mt-10 font-mono text-[12px] uppercase tracking-[0.2em] text-text-dim">
          All plans include SSL encryption · GDPR compliant · 99.9% uptime SLA
        </p>
      </div>
    </section>
  );
}
