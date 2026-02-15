"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    const supabase = createClient();
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    setLoading(false);

    if (signInError) {
      setError(signInError.message || "Invalid email or password.");
    } else {
      router.push("/chat");
      router.refresh();
    }
  };

  const handleGoogleLogin = async () => {
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=/chat` },
    });
  };

  return (
    <div className="min-h-screen bg-void flex flex-col">
      {/* Header */}
      <header className="w-full px-6 py-5">
        <Link href="/" className="flex items-center gap-3 group w-fit">
          <span className="text-secondary text-lg font-bold tracking-tight">
            &#x25C8;
          </span>
          <span className="text-text-primary text-sm font-semibold tracking-[0.15em] uppercase">
            Hunt
          </span>
        </Link>
      </header>

      {/* Main */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          {/* Heading */}
          <div className="text-center mb-8">
            <h1 className="font-mono text-2xl md:text-3xl font-bold text-text-primary tracking-tight mb-3">
              Welcome Back
            </h1>
            <p className="font-sans text-sm text-text-muted leading-relaxed">
              Log in to continue hunting leads.
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 text-sm text-red-400 font-sans">
                {error}
              </div>
            )}
            <div>
              <label className="block font-mono text-[12px] uppercase tracking-[0.2em] text-text-muted mb-2">
                Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@company.com"
                className="w-full bg-surface-2 border border-border rounded-lg px-4 py-3 text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block font-mono text-[12px] uppercase tracking-[0.2em] text-text-muted">
                  Password
                </label>
                <a
                  href="#"
                  className="font-mono text-[12px] text-secondary/60 hover:text-secondary transition-colors"
                >
                  Forgot password?
                </a>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full bg-surface-2 border border-border rounded-lg px-4 py-3 text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] py-4 rounded-lg hover:bg-white/85 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer mt-2"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-void/30 border-t-void rounded-full animate-spin" />
                  Logging in...
                </span>
              ) : (
                "Log In"
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border-dim" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="px-3 bg-void text-text-dim font-mono text-[12px] uppercase tracking-widest">
                or continue with
              </span>
            </div>
          </div>

          {/* Google login */}
          <button
            type="button"
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-2 bg-surface-2 border border-border rounded-lg py-3 text-text-muted hover:text-text-secondary hover:border-border-bright transition-colors cursor-pointer"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            <span className="font-mono text-[12px] uppercase tracking-[0.1em]">Continue with Google</span>
          </button>

          {/* Sign up link */}
          <p className="text-center mt-8 font-sans text-sm text-text-muted">
            Don&apos;t have an account?{" "}
            <Link
              href="/signup"
              className="text-secondary/70 hover:text-secondary transition-colors"
            >
              Sign up free
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
