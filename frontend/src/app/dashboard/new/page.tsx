"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "../../components/auth/SessionProvider";
import { useHunt } from "../../components/hunt/HuntContext";
import { usePipelineTracker, type LaunchPipelineConfig } from "../../components/pipeline/PipelineTracker";

type Tab = "configure" | "guided" | "bulk";

interface Template {
  id: string;
  name: string;
  search_context: Record<string, string>;
  created_at: string;
}

export default function NewPipelinePage() {
  const router = useRouter();
  const { session } = useAuth();
  const { resetHunt } = useHunt();
  const { launchPipeline } = usePipelineTracker();

  const [tab, setTab] = useState<Tab>("configure");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);

  // Form state
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [companyProfile, setCompanyProfile] = useState("");
  const [technologyFocus, setTechnologyFocus] = useState("");
  const [qualifyingCriteria, setQualifyingCriteria] = useState("");
  const [disqualifiers, setDisqualifiers] = useState("");
  const [geographicRegion, setGeographicRegion] = useState("");
  const [countryCode, setCountryCode] = useState("");
  const [maxLeads, setMaxLeads] = useState(100);

  // Bulk import state
  const [bulkDomains, setBulkDomains] = useState("");

  // Load templates
  useEffect(() => {
    if (!session?.access_token) return;
    fetch("/api/proxy/templates", {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setTemplates(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [session]);

  const loadTemplate = (tmpl: Template) => {
    const ctx = tmpl.search_context || {};
    setIndustry(ctx.industry || "");
    setCompanyProfile(ctx.company_profile || "");
    setTechnologyFocus(ctx.technology_focus || "");
    setQualifyingCriteria(ctx.qualifying_criteria || "");
    setDisqualifiers(ctx.disqualifiers || "");
    setGeographicRegion(ctx.geographic_region || "");
    setName(tmpl.name);
  };

  const canLaunchDiscover = industry.trim() && technologyFocus.trim();
  const canLaunchBulk = bulkDomains.trim().split("\n").filter((d) => d.trim()).length > 0;

  const handleLaunchDiscover = async () => {
    if (!canLaunchDiscover) return;
    setLaunching(true);
    setError(null);

    try {
      resetHunt();

      const config: LaunchPipelineConfig = {
        mode: "discover",
        name: name.trim() || undefined,
        search_context: {
          industry: industry.trim(),
          company_profile: companyProfile.trim() || undefined,
          technology_focus: technologyFocus.trim(),
          qualifying_criteria: qualifyingCriteria.trim() || undefined,
          disqualifiers: disqualifiers.trim() || undefined,
          geographic_region: geographicRegion.trim() || undefined,
        },
        country_code: countryCode.trim() || undefined,
        options: { use_vision: true, max_leads: maxLeads },
      };

      await launchPipeline(config);
      router.push("/dashboard/pipeline");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create pipeline");
      setLaunching(false);
    }
  };

  const handleLaunchBulk = async () => {
    if (!canLaunchBulk) return;
    setLaunching(true);
    setError(null);

    try {
      resetHunt();

      const domains = bulkDomains
        .split("\n")
        .map((d) => d.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0])
        .filter((d) => d && d.includes("."));

      const config: LaunchPipelineConfig = {
        mode: "qualify_only",
        name: name.trim() || `Bulk import (${domains.length} domains)`,
        domains,
        search_context: industry.trim()
          ? {
              industry: industry.trim(),
              company_profile: companyProfile.trim() || undefined,
              technology_focus: technologyFocus.trim() || undefined,
              qualifying_criteria: qualifyingCriteria.trim() || undefined,
              disqualifiers: disqualifiers.trim() || undefined,
              geographic_region: geographicRegion.trim() || undefined,
            }
          : undefined,
        options: { use_vision: true },
      };

      await launchPipeline(config);
      router.push("/dashboard/pipeline");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create pipeline");
      setLaunching(false);
    }
  };

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    {
      id: "configure",
      label: "Configure",
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
        </svg>
      ),
    },
    {
      id: "guided",
      label: "Guided (Chat)",
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
        </svg>
      ),
    },
    {
      id: "bulk",
      label: "Bulk Import",
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
      ),
    },
  ];

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <button
          onClick={() => router.push(localStorage.getItem("lastDashboardTab") || "/dashboard")}
          className="font-mono text-[10px] text-text-dim hover:text-text-muted uppercase tracking-[0.15em] transition-colors cursor-pointer"
        >
          &larr; Dashboard
        </button>
        <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight mt-2">
          New Pipeline
        </h1>
        <p className="font-sans text-sm text-text-muted mt-1">
          Choose how to discover and qualify leads
        </p>
      </div>

      {/* Tab selector */}
      <div className="flex gap-1 bg-surface-2 border border-border rounded-xl p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 flex items-center justify-center gap-2 font-mono text-xs uppercase tracking-[0.1em] py-3 rounded-lg transition-all cursor-pointer ${
              tab === t.id
                ? "bg-secondary/10 text-secondary border border-secondary/20"
                : "text-text-muted hover:text-text-primary border border-transparent"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
          <p className="font-mono text-xs text-red-400">{error}</p>
        </div>
      )}

      {/* ── Configure tab ── */}
      {tab === "configure" && (
        <div className="space-y-6">
          {/* Templates */}
          {templates.length > 0 && (
            <div className="space-y-2">
              <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
                Load from template
              </label>
              <div className="flex flex-wrap gap-2">
                {templates.map((tmpl) => (
                  <button
                    key={tmpl.id}
                    onClick={() => loadTemplate(tmpl)}
                    className="font-mono text-[10px] border border-border text-text-muted hover:text-secondary hover:border-secondary/30 px-3 py-2 rounded-lg transition-colors cursor-pointer"
                  >
                    {tmpl.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Form */}
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                Pipeline Name <span className="text-text-dim">(optional)</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. CNC Manufacturers DACH"
                className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                  Industry <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  placeholder="e.g. CNC machining, precision manufacturing"
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
                />
              </div>

              <div>
                <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                  Technology / Products <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={technologyFocus}
                  onChange={(e) => setTechnologyFocus(e.target.value)}
                  placeholder="e.g. 5-axis CNC, turning, milling"
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                Company Profile
              </label>
              <input
                type="text"
                value={companyProfile}
                onChange={(e) => setCompanyProfile(e.target.value)}
                placeholder="e.g. Manufacturers with 50-500 employees, B2B focus"
                className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                  Qualifying Criteria
                </label>
                <textarea
                  value={qualifyingCriteria}
                  onChange={(e) => setQualifyingCriteria(e.target.value)}
                  placeholder="e.g. Has product catalog, serves B2B customers, ships internationally"
                  rows={3}
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors resize-none"
                />
              </div>

              <div>
                <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                  Disqualifiers
                </label>
                <textarea
                  value={disqualifiers}
                  onChange={(e) => setDisqualifiers(e.target.value)}
                  placeholder="e.g. Pure distributor, no manufacturing, closed company"
                  rows={3}
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors resize-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div>
                <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                  Geographic Region
                </label>
                <input
                  type="text"
                  value={geographicRegion}
                  onChange={(e) => setGeographicRegion(e.target.value)}
                  placeholder="e.g. Germany, Austria, Switzerland"
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
                />
              </div>

              <div>
                <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                  Country Code
                </label>
                <input
                  type="text"
                  value={countryCode}
                  onChange={(e) => setCountryCode(e.target.value.toUpperCase().slice(0, 2))}
                  placeholder="e.g. DE"
                  maxLength={2}
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
                />
              </div>

              <div>
                <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                  Max Leads
                </label>
                <input
                  type="number"
                  value={maxLeads}
                  onChange={(e) => setMaxLeads(Math.max(1, Math.min(500, Number(e.target.value))))}
                  min={1}
                  max={500}
                  className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
                />
              </div>
            </div>
          </div>

          {/* Launch button */}
          <button
            onClick={handleLaunchDiscover}
            disabled={!canLaunchDiscover || launching}
            className="w-full flex items-center justify-center gap-3 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-6 py-4 rounded-xl hover:bg-white/85 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            {launching ? (
              <>
                <div className="w-4 h-4 border-2 border-void/30 border-t-void rounded-full animate-spin" />
                Launching Pipeline...
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                Launch Discovery Pipeline
              </>
            )}
          </button>

          <p className="font-mono text-[10px] text-text-dim text-center">
            AI agents will search the web, crawl company sites, and qualify leads automatically.
          </p>
        </div>
      )}

      {/* ── Guided (Chat) tab ── */}
      {tab === "guided" && (
        <div className="bg-surface-2 border border-border rounded-xl p-8 text-center space-y-4">
          <div className="w-12 h-12 mx-auto bg-secondary/10 border border-secondary/20 rounded-xl flex items-center justify-center">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-secondary">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            </svg>
          </div>
          <h2 className="font-mono text-sm font-semibold text-text-primary">
            Guided Discovery
          </h2>
          <p className="font-sans text-sm text-text-muted max-w-md mx-auto">
            Describe your ideal customer in plain language. The AI assistant will ask clarifying
            questions and build the perfect search configuration for you.
          </p>
          <p className="font-mono text-[10px] text-text-dim">
            Best for: new ICPs, exploring unfamiliar markets, first-time users
          </p>
          <Link
            href="/chat"
            onClick={() => resetHunt()}
            className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-6 py-3 rounded-lg hover:bg-secondary/20 transition-colors"
          >
            Open Chat Assistant &rarr;
          </Link>
        </div>
      )}

      {/* ── Bulk Import tab ── */}
      {tab === "bulk" && (
        <div className="space-y-6">
          <div className="bg-surface-2 border border-border rounded-xl p-6 space-y-5">
            <div>
              <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted block mb-2">
                Domains <span className="text-red-400">*</span>
                <span className="text-text-dim ml-2">(one per line)</span>
              </label>
              <textarea
                value={bulkDomains}
                onChange={(e) => setBulkDomains(e.target.value)}
                placeholder={"acme-cnc.de\nprecision-parts.com\nmetal-works.at\n..."}
                rows={8}
                className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors resize-none"
              />
              <p className="font-mono text-[10px] text-text-dim mt-2">
                {bulkDomains.split("\n").filter((d) => d.trim()).length} domains entered
              </p>
            </div>

            {/* Optional: ICP context for scoring */}
            <details className="group">
              <summary className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted cursor-pointer hover:text-text-primary transition-colors">
                + Add ICP context for better scoring
              </summary>
              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim block mb-2">
                      Industry
                    </label>
                    <input
                      type="text"
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                      placeholder="e.g. Manufacturing"
                      className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
                    />
                  </div>
                  <div>
                    <label className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim block mb-2">
                      Technology
                    </label>
                    <input
                      type="text"
                      value={technologyFocus}
                      onChange={(e) => setTechnologyFocus(e.target.value)}
                      placeholder="e.g. CNC machining"
                      className="w-full bg-surface-3 border border-border rounded-lg px-4 py-3 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
                    />
                  </div>
                </div>
              </div>
            </details>
          </div>

          <button
            onClick={handleLaunchBulk}
            disabled={!canLaunchBulk || launching}
            className="w-full flex items-center justify-center gap-3 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-6 py-4 rounded-xl hover:bg-white/85 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            {launching ? (
              <>
                <div className="w-4 h-4 border-2 border-void/30 border-t-void rounded-full animate-spin" />
                Processing Domains...
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                Qualify {bulkDomains.split("\n").filter((d) => d.trim()).length} Domains
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
