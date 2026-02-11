"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../../components/auth/SessionProvider";

interface UsageData {
  searches: number;
  leads: number;
  enrichments: number;
  cost: number;
}

interface BillingData {
  plan: string;
  status: string;
  period_end: string | null;
  has_subscription: boolean;
  usage: {
    plan: string;
    searches_run: number;
    searches_limit: number | null;
    leads_qualified: number;
    leads_limit: number | null;
    enrichments_used: number;
    enrichments_limit: number | null;
    leads_per_hunt: number;
    deep_research: boolean;
  };
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SettingsPage() {
  const { session, user } = useAuth();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [billing, setBilling] = useState<BillingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkingOut, setCheckingOut] = useState(false);
  const [apiStatus, setApiStatus] = useState<{
    backend: boolean;
    checked: boolean;
  }>({ backend: false, checked: false });

  useEffect(() => {
    if (!session?.access_token) return;
    const headers = { Authorization: `Bearer ${session.access_token}` };

    Promise.all([
      // Health/usage check
      fetch(`${API}/api/usage`, { headers })
        .then((r) => {
          setApiStatus({ backend: r.ok, checked: true });
          return r.ok ? r.json() : null;
        })
        .then((data) => {
          if (data) {
            setUsage({
              searches: data.searches_run ?? 0,
              leads: data.leads_qualified ?? 0,
              enrichments: data.enrichments_used ?? 0,
              cost: 0,
            });
          }
        })
        .catch(() => setApiStatus({ backend: false, checked: true })),
      // Billing status
      fetch("/api/billing/status", { headers })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data) setBilling(data);
        })
        .catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [session]);

  const handleCheckout = async (plan: string) => {
    if (!session?.access_token) return;
    setCheckingOut(true);
    try {
      const resp = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ plan }),
      });
      const data = await resp.json();
      if (data.url) window.location.href = data.url;
    } catch (e) {
      console.error("Checkout error:", e);
    } finally {
      setCheckingOut(false);
    }
  };

  const handlePortal = async () => {
    if (!session?.access_token) return;
    try {
      const resp = await fetch("/api/billing/portal", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
      });
      const data = await resp.json();
      if (data.url) window.location.href = data.url;
    } catch (e) {
      console.error("Portal error:", e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-6 h-6 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-3xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">
          Settings
        </h1>
        <p className="font-sans text-sm text-text-muted mt-1">
          Account, API status, and usage
        </p>
      </div>

      {/* Account */}
      <section className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-border-dim">
          <h2 className="font-mono text-xs font-semibold text-text-primary uppercase tracking-[0.12em]">
            Account
          </h2>
        </div>
        <div className="px-5 py-4 space-y-3">
          <Row label="Email" value={user?.email || "—"} />
          <Row label="User ID" value={user?.id?.slice(0, 12) + "…" || "—"} mono />
          <Row
            label="Plan"
            value={(billing?.plan || "free").charAt(0).toUpperCase() + (billing?.plan || "free").slice(1)}
            badge={billing?.status === "active" ? "Active" : "Current"}
          />
          {billing?.period_end && (
            <Row
              label="Renews"
              value={new Date(billing.period_end).toLocaleDateString()}
            />
          )}
        </div>
      </section>

      {/* Billing / Plan */}
      <section className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-border-dim">
          <h2 className="font-mono text-xs font-semibold text-text-primary uppercase tracking-[0.12em]">
            Plan &amp; Billing
          </h2>
        </div>
        <div className="px-5 py-4">
          {billing?.plan === "free" ? (
            <div className="space-y-3">
              <p className="font-sans text-xs text-text-muted">
                You&apos;re on the Free plan. Upgrade for more hunts, leads, and deep research.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => handleCheckout("pro")}
                  disabled={checkingOut}
                  className="font-mono text-[10px] uppercase tracking-[0.15em] px-4 py-2.5 rounded-lg bg-text-primary text-void hover:bg-white/85 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {checkingOut ? "Redirecting…" : "Upgrade to Pro — $49/mo"}
                </button>
                <button
                  onClick={() => handleCheckout("enterprise")}
                  disabled={checkingOut}
                  className="font-mono text-[10px] uppercase tracking-[0.15em] px-4 py-2.5 rounded-lg border border-border text-text-secondary hover:border-border-bright hover:text-text-primary transition-colors cursor-pointer disabled:opacity-50"
                >
                  Enterprise — $199/mo
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="font-sans text-xs text-text-muted">
                You&apos;re on the{" "}
                <span className="text-secondary font-semibold">
                  {billing?.plan?.charAt(0).toUpperCase()}{billing?.plan?.slice(1)}
                </span>{" "}
                plan.
              </p>
              <button
                onClick={handlePortal}
                className="font-mono text-[10px] uppercase tracking-[0.15em] px-4 py-2.5 rounded-lg border border-border text-text-secondary hover:border-border-bright hover:text-text-primary transition-colors cursor-pointer"
              >
                Manage Subscription
              </button>
            </div>
          )}
        </div>
      </section>

      {/* API Status */}
      <section className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-border-dim">
          <h2 className="font-mono text-xs font-semibold text-text-primary uppercase tracking-[0.12em]">
            API Status
          </h2>
        </div>
        <div className="px-5 py-4 space-y-3">
          <StatusRow
            label="Backend API"
            ok={apiStatus.backend}
            checked={apiStatus.checked}
          />
          <StatusRow
            label="Supabase Auth"
            ok={!!session?.access_token}
            checked={true}
          />
          <StatusRow
            label="Mapbox Token"
            ok={!!process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
            checked={true}
          />
        </div>
      </section>

      {/* Usage */}
      <section className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-border-dim">
          <h2 className="font-mono text-xs font-semibold text-text-primary uppercase tracking-[0.12em]">
            Monthly Usage
          </h2>
        </div>
        <div className="px-5 py-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <UsageStat label="Searches" value={usage?.searches ?? 0} />
            <UsageStat label="Leads" value={usage?.leads ?? 0} />
            <UsageStat label="Enrichments" value={usage?.enrichments ?? 0} />
            <UsageStat
              label="Deep Research"
              value={billing?.usage?.deep_research ? "✓" : "—"}
            />
          </div>

          {/* Usage bars */}
          {billing?.usage && (
            <div className="mt-5 pt-4 border-t border-border-dim space-y-3">
              <UsageBar
                label="Hunts"
                used={billing.usage.searches_run}
                limit={billing.usage.searches_limit}
              />
              <UsageBar
                label="Leads"
                used={billing.usage.leads_qualified}
                limit={billing.usage.leads_limit}
              />
              <UsageBar
                label="Enrichments"
                used={billing.usage.enrichments_used}
                limit={billing.usage.enrichments_limit}
              />
            </div>
          )}
        </div>
      </section>

      {/* Danger Zone */}
      <section className="bg-surface-2 border border-red-500/20 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-red-500/10">
          <h2 className="font-mono text-xs font-semibold text-red-400 uppercase tracking-[0.12em]">
            Danger Zone
          </h2>
        </div>
        <div className="px-5 py-4">
          <p className="font-sans text-xs text-text-muted mb-3">
            Signing out will clear your session. All data is safely stored.
          </p>
          <button
            onClick={async () => {
              const { createBrowserClient } = await import(
                "@supabase/ssr"
              );
              const supabase = createBrowserClient(
                process.env.NEXT_PUBLIC_SUPABASE_URL!,
                process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
              );
              await supabase.auth.signOut();
              window.location.href = "/";
            }}
            className="font-mono text-[10px] uppercase tracking-[0.15em] px-4 py-2.5 rounded-lg border border-red-500/20 text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer"
          >
            Sign Out
          </button>
        </div>
      </section>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  badge,
}: {
  label: string;
  value: string;
  mono?: boolean;
  badge?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[10px] text-text-dim uppercase tracking-[0.15em]">
        {label}
      </span>
      <div className="flex items-center gap-2">
        <span
          className={`text-xs text-text-primary ${mono ? "font-mono" : "font-sans"}`}
        >
          {value}
        </span>
        {badge && (
          <span className="font-mono text-[9px] px-2 py-0.5 rounded bg-secondary/10 text-secondary border border-secondary/20">
            {badge}
          </span>
        )}
      </div>
    </div>
  );
}

function StatusRow({
  label,
  ok,
  checked,
}: {
  label: string;
  ok: boolean;
  checked: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[10px] text-text-dim uppercase tracking-[0.15em]">
        {label}
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className={`w-2 h-2 rounded-full ${
            !checked
              ? "bg-text-dim animate-pulse"
              : ok
                ? "bg-green-400"
                : "bg-red-400"
          }`}
        />
        <span
          className={`font-mono text-[10px] ${
            !checked
              ? "text-text-dim"
              : ok
                ? "text-green-400"
                : "text-red-400"
          }`}
        >
          {!checked ? "Checking…" : ok ? "Connected" : "Unavailable"}
        </span>
      </span>
    </div>
  );
}

function UsageStat({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="text-center">
      <span className="font-mono text-lg font-bold text-text-primary block">
        {value}
      </span>
      <span className="font-mono text-[9px] text-text-muted uppercase tracking-[0.15em]">
        {label}
      </span>
    </div>
  );
}

function UsageBar({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number | null;
}) {
  if (limit === null) {
    return (
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em]">
          {label}
        </span>
        <span className="font-mono text-xs text-text-primary">
          {used} / ∞
        </span>
      </div>
    );
  }

  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em]">
          {label}
        </span>
        <span className="font-mono text-xs text-text-primary">
          {used} / {limit}
        </span>
      </div>
      <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            pct >= 90 ? "bg-red-400" : pct >= 70 ? "bg-amber-400" : "bg-secondary"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
