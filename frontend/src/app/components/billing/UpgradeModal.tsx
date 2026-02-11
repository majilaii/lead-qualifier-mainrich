"use client";

import { useBilling } from "./BillingProvider";

const PLANS = [
  {
    id: "free" as const,
    name: "Free",
    price: "$0",
    period: "forever",
    features: [
      "3 hunts / month",
      "25 leads per hunt",
      "10 contact enrichments",
      "Basic AI qualification",
      "CSV export",
    ],
  },
  {
    id: "pro" as const,
    name: "Pro",
    price: "$49",
    period: "/month",
    highlight: true,
    features: [
      "20 hunts / month",
      "100 leads per hunt",
      "200 contact enrichments",
      "Deep research briefs",
      "Priority support",
    ],
  },
  {
    id: "enterprise" as const,
    name: "Enterprise",
    price: "$199",
    period: "/month",
    features: [
      "Unlimited hunts",
      "500 leads per hunt",
      "1,000 contact enrichments",
      "Deep research + priority",
      "Dedicated support",
    ],
  },
];

export default function UpgradeModal() {
  const { showUpgrade, setShowUpgrade, checkout, billing, quotaError } =
    useBilling();

  if (!showUpgrade) return null;

  const currentPlan = billing?.plan || "free";

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-void/80 backdrop-blur-sm"
        onClick={() => {
          setShowUpgrade(false);
        }}
      />

      {/* Modal */}
      <div className="relative bg-surface-2 border border-border rounded-2xl max-w-3xl w-full mx-4 p-8 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        {/* Close button */}
        <button
          onClick={() => setShowUpgrade(false)}
          className="absolute top-4 right-4 text-text-dim hover:text-text-primary transition-colors"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>

        {/* Header */}
        <div className="text-center mb-8">
          {quotaError ? (
            <>
              <div className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-full px-4 py-1.5 mb-4">
                <span className="text-amber-400 text-xs">⚠</span>
                <span className="font-mono text-[10px] text-amber-400 uppercase tracking-wider">
                  Quota Reached
                </span>
              </div>
              <h2 className="font-mono text-xl font-bold text-text-primary mb-2">
                You&apos;ve hit your {quotaError.action} limit
              </h2>
              <p className="font-sans text-sm text-text-muted">
                {quotaError.used} / {quotaError.limit} used this month.
                Upgrade for more capacity.
              </p>
            </>
          ) : (
            <>
              <h2 className="font-mono text-xl font-bold text-text-primary mb-2">
                Upgrade Your Plan
              </h2>
              <p className="font-sans text-sm text-text-muted">
                Unlock more hunts, leads, and deep research.
              </p>
            </>
          )}
        </div>

        {/* Plan cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {PLANS.map((plan) => {
            const isCurrent = plan.id === currentPlan;
            const isUpgrade =
              (currentPlan === "free" && plan.id !== "free") ||
              (currentPlan === "pro" && plan.id === "enterprise");

            return (
              <div
                key={plan.id}
                className={`relative rounded-xl p-5 transition-all ${
                  plan.highlight
                    ? "bg-surface-3 border-2 border-secondary/30"
                    : "bg-surface-1 border border-border"
                }`}
              >
                {plan.highlight && (
                  <div className="absolute -top-2.5 left-1/2 -translate-x-1/2">
                    <span className="bg-secondary text-void font-mono text-[8px] font-bold uppercase tracking-[0.2em] px-2.5 py-0.5 rounded-full">
                      Recommended
                    </span>
                  </div>
                )}

                <h3 className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted mb-3">
                  {plan.name}
                </h3>

                <div className="flex items-baseline gap-1 mb-4">
                  <span className="font-mono text-3xl font-bold text-text-primary">
                    {plan.price}
                  </span>
                  {plan.period && (
                    <span className="font-mono text-xs text-text-dim">
                      {plan.period}
                    </span>
                  )}
                </div>

                <button
                  onClick={() => {
                    if (isUpgrade) {
                      checkout(plan.id as "pro" | "enterprise");
                    }
                  }}
                  disabled={isCurrent || !isUpgrade}
                  className={`w-full text-center font-mono text-[10px] font-bold uppercase tracking-[0.15em] py-3 rounded-lg transition-colors mb-4 cursor-pointer ${
                    isCurrent
                      ? "bg-secondary/10 text-secondary border border-secondary/20"
                      : isUpgrade
                        ? "bg-text-primary text-void hover:bg-white/85"
                        : "bg-surface-3 text-text-dim border border-border cursor-not-allowed"
                  }`}
                >
                  {isCurrent ? "Current Plan" : isUpgrade ? "Upgrade" : "—"}
                </button>

                <ul className="space-y-2">
                  {plan.features.map((feat) => (
                    <li key={feat} className="flex items-start gap-2">
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        className="text-secondary/60 flex-shrink-0 mt-0.5"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      <span className="font-sans text-[11px] text-text-secondary">
                        {feat}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        <p className="text-center mt-6 font-mono text-[9px] text-text-dim uppercase tracking-wider">
          Powered by Stripe · Cancel anytime · SSL encrypted
        </p>
      </div>
    </div>
  );
}
