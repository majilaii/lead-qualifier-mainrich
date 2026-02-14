"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "./SessionProvider";
import { createClient } from "@/lib/supabase/client";

export default function UserMenu() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Link
          href="/login"
          className="font-mono text-[10px] text-text-muted hover:text-text-primary uppercase tracking-[0.15em] transition-colors px-3 py-1.5"
        >
          Log in
        </Link>
        <Link
          href="/signup"
          className="font-mono text-[10px] text-void bg-text-primary hover:bg-white/85 uppercase tracking-[0.15em] transition-colors px-3 py-1.5 rounded-lg"
        >
          Sign up
        </Link>
      </div>
    );
  }

  const displayName =
    user.user_metadata?.full_name ||
    user.user_metadata?.name ||
    user.email ||
    "?";
  const initials = displayName
    .split(" ")
    .map((p: string) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const handleSignOut = async () => {
    setOpen(false);
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/");
    router.refresh();
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-full bg-secondary/20 border border-secondary/30 flex items-center justify-center text-secondary font-mono text-[10px] font-bold hover:bg-secondary/30 transition-colors cursor-pointer"
      >
        {initials}
      </button>

      {open && (
        <div className="absolute right-0 bottom-10 w-52 bg-surface-2 border border-border rounded-xl shadow-lg z-50 overflow-hidden animate-slide-up">
          <div className="px-4 py-3 border-b border-border-dim">
            <p className="font-mono text-xs text-text-primary truncate">
              {displayName}
            </p>
            <p className="font-mono text-[10px] text-text-dim truncate">
              {user.email}
            </p>
          </div>
          <div className="py-1">
            <Link
              href="/dashboard"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted hover:text-text-primary hover:bg-surface-3 transition-colors"
            >
              Dashboard
            </Link>
            <button
              onClick={handleSignOut}
              className="w-full text-left px-4 py-2 font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted hover:text-red-400 hover:bg-surface-3 transition-colors cursor-pointer"
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
