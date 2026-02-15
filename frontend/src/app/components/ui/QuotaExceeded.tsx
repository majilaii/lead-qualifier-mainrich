"use client";

import Link from "next/link";

interface QuotaExceededProps {
  type: "pipelines" | "leads" | "enrichments" | "email_drafts";
  current: number;
  limit: number;
  plan: string;
}

const TYPE_LABELS: Record<QuotaExceededProps["type"], string> = {
  pipelines: "pipeline runs",
  leads: "leads",
  enrichments: "enrichments",
  email_drafts: "email drafts",
};

export function QuotaExceeded({ type, current, limit, plan }: QuotaExceededProps) {
  const label = TYPE_LABELS[type];

  return (
    <div className="bg-surface-2 border border-amber-500/20 rounded-xl p-8 text-center">
      <p className="font-mono text-sm text-text-primary mb-2">
        Monthly limit reached
      </p>
      <p className="font-mono text-xs text-text-dim mb-2 max-w-sm mx-auto">
        You&apos;ve used {current}/{limit} {label} this month on the{" "}
        <span className="text-text-muted capitalize">{plan}</span> plan.
      </p>
      <p className="font-mono text-xs text-text-dim mb-6 max-w-sm mx-auto">
        Upgrade to Pro for higher limits + scheduling.
      </p>
      <Link
        href="/dashboard/settings"
        className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-white/85 transition-colors"
      >
        Upgrade to Pro — $49/mo
      </Link>
    </div>
  );
}
