"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AuthGuard from "../components/auth/AuthGuard";
import UserMenu from "../components/auth/UserMenu";
import { useHunt } from "../components/hunt/HuntContext";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: "◈" },
  { href: "/dashboard/hunts", label: "Hunts", icon: "🔍" },
  { href: "/dashboard/pipeline", label: "Pipeline", icon: "📊" },
  { href: "/dashboard/map", label: "Map", icon: "🗺️" },
  { href: "/dashboard/settings", label: "Settings", icon: "⚙️" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { phase, isPipelineRunning, qualifiedCompanies, searchCompanies, pipelineProgress, resetHunt } = useHunt();

  // Pipeline is "active" when searching, qualifying, search-complete, or just completed
  const huntActive = phase !== "chat";
  const huntSpinning = phase === "searching" || phase === "qualifying";

  return (
    <AuthGuard>
      <div className="flex h-dvh bg-void">
        {/* Sidebar */}
        <aside className="hidden md:flex flex-col w-56 border-r border-border-dim bg-surface-1/50">
          {/* Logo */}
          <div className="h-14 flex items-center px-5 border-b border-border-dim">
            <Link href="/" className="flex items-center gap-2.5 group">
              <span className="text-secondary text-base font-bold">◈</span>
              <span className="text-text-primary text-xs font-semibold tracking-[0.12em] uppercase group-hover:text-secondary transition-colors">
                Hunt
              </span>
            </Link>
          </div>

          {/* Nav links */}
          <nav className="flex-1 py-4 px-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const isActive =
                item.href === "/dashboard"
                  ? pathname === "/dashboard"
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-mono uppercase tracking-[0.1em] transition-all duration-200 ${
                    isActive
                      ? "bg-secondary/10 text-secondary border border-secondary/20"
                      : "text-text-muted hover:text-text-primary hover:bg-surface-3/50 border border-transparent"
                  }`}
                >
                  <span className="text-sm">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Pipeline status (sidebar) */}
          {huntActive && (
            <div className="px-3 pb-2">
              <Link
                href="/chat"
                className="flex items-center gap-2.5 bg-secondary/10 border border-secondary/20 rounded-lg px-3 py-2.5 hover:bg-secondary/15 transition-colors group"
              >
                {huntSpinning ? (
                  <div className="w-3 h-3 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin flex-shrink-0" />
                ) : (
                  <span className="text-secondary text-xs flex-shrink-0">◈</span>
                )}
                <div className="flex-1 min-w-0">
                  <span className="font-mono text-[10px] text-secondary block truncate">
                    {phase === "searching" && "Searching..."}
                    {phase === "search-complete" && `${searchCompanies.length} found — pick batch`}
                    {phase === "qualifying" && `Qualifying ${qualifiedCompanies.length}/${searchCompanies.length}`}
                    {phase === "complete" && `Done — ${qualifiedCompanies.filter(c => c.tier === "hot").length} hot leads`}
                  </span>
                  {pipelineProgress && (
                    <span className="font-mono text-[9px] text-secondary/50 block truncate">
                      {pipelineProgress.phase === "crawling" ? "Crawling" : "Analyzing"} {pipelineProgress.company}
                    </span>
                  )}
                </div>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-secondary/40 group-hover:text-secondary flex-shrink-0">
                  <path d="M9 18l6-6-6-6" />
                </svg>
              </Link>
            </div>
          )}

          {/* Quick action */}
          <div className="px-3 pb-3">
            <button
              onClick={() => { resetHunt(); router.push("/chat"); }}
              className="flex items-center justify-center gap-2 bg-text-primary text-void font-mono text-[10px] font-bold uppercase tracking-[0.15em] px-4 py-3 rounded-lg hover:bg-white/85 transition-colors w-full cursor-pointer"
            >
              + New Hunt
            </button>
          </div>

          {/* User menu */}
          <div className="px-3 pb-4 border-t border-border-dim pt-3">
            <UserMenu />
          </div>
        </aside>

        {/* Mobile bottom nav */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-surface-1/95 backdrop-blur-md border-t border-border-dim flex justify-around py-2 px-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center gap-0.5 px-2 py-1 rounded-lg text-[9px] font-mono uppercase tracking-[0.1em] transition-colors ${
                  isActive ? "text-secondary" : "text-text-dim"
                }`}
              >
                <span className="text-base">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Floating pipeline pill (mobile) */}
        {huntActive && (
          <Link
            href="/chat"
            className="md:hidden fixed bottom-16 left-4 right-4 z-50 flex items-center gap-2.5 bg-surface-2/95 backdrop-blur-md border border-secondary/30 rounded-xl px-4 py-3 shadow-lg"
          >
            {huntSpinning ? (
              <div className="w-3 h-3 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin flex-shrink-0" />
            ) : (
              <span className="text-secondary text-xs flex-shrink-0">◈</span>
            )}
            <span className="font-mono text-[10px] text-secondary flex-1 truncate">
              {phase === "searching" && "Searching the web..."}
              {phase === "search-complete" && `${searchCompanies.length} companies found`}
              {phase === "qualifying" && `Qualifying ${qualifiedCompanies.length}/${searchCompanies.length}`}
              {phase === "complete" && `Done — ${qualifiedCompanies.filter(c => c.tier === "hot").length} hot leads`}
            </span>
            <span className="font-mono text-[9px] text-secondary/50 uppercase tracking-[0.15em] flex-shrink-0">View →</span>
          </Link>
        )}

        {/* Main content */}
        <main className="flex-1 overflow-y-auto pb-20 md:pb-0">{children}</main>
      </div>
    </AuthGuard>
  );
}
