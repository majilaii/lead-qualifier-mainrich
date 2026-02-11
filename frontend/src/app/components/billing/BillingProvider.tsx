"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { useAuth } from "../auth/SessionProvider";

/* ═══════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════ */

interface BillingStatus {
  plan: "free" | "pro" | "enterprise";
  status: string;
  period_end: string | null;
  has_subscription: boolean;
  usage: {
    plan: string;
    year_month: string;
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

interface QuotaExceeded {
  error: "quota_exceeded";
  action: string;
  metric: string;
  limit: number;
  used: number;
  plan: string;
  upgrade_url: string;
}

interface BillingContext {
  billing: BillingStatus | null;
  loading: boolean;
  refreshBilling: () => Promise<void>;
  checkout: (plan: "pro" | "enterprise") => Promise<void>;
  openPortal: () => Promise<void>;
  showUpgrade: boolean;
  setShowUpgrade: (show: boolean) => void;
  quotaError: QuotaExceeded | null;
  handleQuotaError: (error: QuotaExceeded) => void;
}

const BillingCtx = createContext<BillingContext>({
  billing: null,
  loading: true,
  refreshBilling: async () => {},
  checkout: async () => {},
  openPortal: async () => {},
  showUpgrade: false,
  setShowUpgrade: () => {},
  quotaError: null,
  handleQuotaError: () => {},
});

export const useBilling = () => useContext(BillingCtx);

/* ═══════════════════════════════════════════════
   Provider
   ═══════════════════════════════════════════════ */

export default function BillingProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [quotaError, setQuotaError] = useState<QuotaExceeded | null>(null);

  const refreshBilling = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const resp = await fetch("/api/billing/status", {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        setBilling(data);
      }
    } catch {
      // silent fail
    } finally {
      setLoading(false);
    }
  }, [session]);

  // Auto-fetch on mount
  useState(() => {
    if (session?.access_token) refreshBilling();
  });

  const checkout = useCallback(
    async (plan: "pro" | "enterprise") => {
      if (!session?.access_token) return;
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
        if (data.url) {
          window.location.href = data.url;
        }
      } catch (e) {
        console.error("Checkout error:", e);
      }
    },
    [session]
  );

  const openPortal = useCallback(async () => {
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
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (e) {
      console.error("Portal error:", e);
    }
  }, [session]);

  const handleQuotaError = useCallback((error: QuotaExceeded) => {
    setQuotaError(error);
    setShowUpgrade(true);
  }, []);

  return (
    <BillingCtx.Provider
      value={{
        billing,
        loading,
        refreshBilling,
        checkout,
        openPortal,
        showUpgrade,
        setShowUpgrade,
        quotaError,
        handleQuotaError,
      }}
    >
      {children}
    </BillingCtx.Provider>
  );
}
