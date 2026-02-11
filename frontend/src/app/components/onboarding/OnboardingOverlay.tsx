"use client";

import { useState, useEffect } from "react";
import { useAuth } from "../auth/SessionProvider";

const STEPS = [
  {
    icon: "💬",
    title: "Describe Your Ideal Customer",
    description:
      "Tell us about the companies you're looking for — industry, size, technology, location. Our AI will ask follow-up questions to sharpen the search.",
  },
  {
    icon: "🔍",
    title: "We Find Hidden Opportunities",
    description:
      "Hunt reads company websites to find leads that databases miss. No LinkedIn presence needed — we crawl the actual product pages.",
  },
  {
    icon: "🎯",
    title: "AI-Qualified Leads, Live",
    description:
      "Watch leads appear on the map in real-time. Each one is scored, categorized, and enriched with deep research — ready for outreach.",
  },
];

interface OnboardingOverlayProps {
  onComplete: () => void;
  onDemo?: () => void;
}

export default function OnboardingOverlay({
  onComplete,
  onDemo,
}: OnboardingOverlayProps) {
  const [step, setStep] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Animate in
    const t = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(t);
  }, []);

  const handleNext = () => {
    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      onComplete();
    }
  };

  return (
    <div
      className={`fixed inset-0 z-[90] flex items-center justify-center transition-all duration-500 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-void/90 backdrop-blur-md" />

      {/* Card */}
      <div className="relative max-w-lg w-full mx-4 bg-surface-2 border border-border rounded-2xl p-8 shadow-2xl">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1 rounded-full transition-all duration-300 ${
                i === step
                  ? "w-8 bg-secondary"
                  : i < step
                    ? "w-4 bg-secondary/40"
                    : "w-4 bg-border"
              }`}
            />
          ))}
        </div>

        {/* Content */}
        <div className="text-center">
          <div className="text-4xl mb-4">{STEPS[step].icon}</div>
          <h2 className="font-mono text-lg font-bold text-text-primary mb-3">
            {STEPS[step].title}
          </h2>
          <p className="font-sans text-sm text-text-muted leading-relaxed max-w-md mx-auto">
            {STEPS[step].description}
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-col items-center gap-3 mt-8">
          <button
            onClick={handleNext}
            className="w-full max-w-xs font-mono text-xs font-bold uppercase tracking-[0.15em] py-3.5 rounded-lg bg-text-primary text-void hover:bg-white/85 transition-colors cursor-pointer"
          >
            {step < STEPS.length - 1 ? "Next" : "Start Hunting →"}
          </button>

          <div className="flex items-center gap-4">
            {step < STEPS.length - 1 && (
              <button
                onClick={onComplete}
                className="font-mono text-[10px] text-text-dim hover:text-text-muted transition-colors cursor-pointer"
              >
                Skip intro
              </button>
            )}
            {onDemo && step === STEPS.length - 1 && (
              <button
                onClick={onDemo}
                className="font-mono text-[10px] text-secondary/60 hover:text-secondary transition-colors cursor-pointer"
              >
                Try with sample data
              </button>
            )}
          </div>
        </div>

        {/* Welcome badge */}
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-secondary text-void font-mono text-[8px] font-bold uppercase tracking-[0.2em] px-3 py-1 rounded-full">
            Welcome to Hunt
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * Hook to detect first-time users.
 * Checks localStorage + optionally the backend for 0 searches.
 */
export function useFirstVisit() {
  const { session, user } = useAuth();
  const [isFirstVisit, setIsFirstVisit] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!user) {
      setChecked(true);
      return;
    }

    // Check localStorage first (fast)
    const key = `hunt_onboarded_${user.id}`;
    if (localStorage.getItem(key) === "true") {
      setIsFirstVisit(false);
      setChecked(true);
      return;
    }

    // Check backend for 0 searches
    const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    if (session?.access_token) {
      fetch(`${API}/api/dashboard/stats`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data && data.total_searches === 0) {
            setIsFirstVisit(true);
          } else {
            // Mark as onboarded
            localStorage.setItem(key, "true");
          }
        })
        .catch(() => {})
        .finally(() => setChecked(true));
    } else {
      setChecked(true);
    }
  }, [user, session]);

  const completeOnboarding = () => {
    if (user) {
      localStorage.setItem(`hunt_onboarded_${user.id}`, "true");
    }
    setIsFirstVisit(false);
  };

  return { isFirstVisit, checked, completeOnboarding };
}
