"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export default function SignUpPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [confirmEmail, setConfirmEmail] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    const supabase = createClient();
    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: name },
      },
    });

    setLoading(false);

    if (signUpError) {
      setError(signUpError.message || "Registration failed. Please try again.");
      return;
    }

    // If email confirmation is required, show a message
    if (data.user && !data.session) {
      setConfirmEmail(true);
      return;
    }

    // Auto-logged in
    router.push("/chat");
    router.refresh();
  };

  const handleGoogleSignup = async () => {
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=/chat` },
    });
  };

  if (confirmEmail) {
    return (
      <div className="min-h-screen bg-void flex flex-col items-center justify-center px-4">
        <div className="text-center max-w-md">
          <div className="text-secondary text-4xl mb-4">✉️</div>
          <h1 className="font-mono text-2xl font-bold text-text-primary tracking-tight mb-3">
            Check Your Email
          </h1>
          <p className="font-sans text-sm text-text-muted leading-relaxed mb-6">
            We sent a confirmation link to <strong className="text-text-primary">{email}</strong>.
            Click it to activate your account, then come back and log in.
          </p>
          <Link
            href="/login"
            className="inline-block bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] py-3 px-6 rounded-lg hover:bg-white/85 transition-colors"
          >
            Go to Login
          </Link>
        </div>
      </div>
    );
  }

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
              Start Hunting for Free
            </h1>
            <p className="font-sans text-sm text-text-muted leading-relaxed">
              50 free leads every month. No credit card required.
              <br />
              Set up in under 2 minutes.
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
                Full Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="Your name"
                className="w-full bg-surface-2 border border-border rounded-lg px-4 py-3 text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
              />
            </div>

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
              <label className="block font-mono text-[12px] uppercase tracking-[0.2em] text-text-muted mb-2">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                placeholder="Min. 8 characters"
                className="w-full bg-surface-2 border border-border rounded-lg px-4 py-3 text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40 transition-colors"
              />
            </div>

            {/* Terms checkbox */}
            <label className="flex items-start gap-3 cursor-pointer py-1">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                className="mt-0.5 accent-secondary"
              />
              <span className="font-sans text-xs text-text-muted leading-relaxed">
                I agree to the{" "}
                <a href="#" className="text-secondary/70 hover:text-secondary">
                  Terms of Service
                </a>{" "}
                and{" "}
                <a href="#" className="text-secondary/70 hover:text-secondary">
                  Privacy Policy
                </a>
              </span>
            </label>

            <button
              type="submit"
              disabled={loading || !agreed}
              className="w-full bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] py-4 rounded-lg hover:bg-white/85 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-void/30 border-t-void rounded-full animate-spin" />
                  Creating account...
                </span>
              ) : (
                "Create Free Account"
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

          {/* Google signup */}
          <button
            type="button"
            onClick={handleGoogleSignup}
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

          {/* Login link */}
          <p className="text-center mt-8 font-sans text-sm text-text-muted">
            Already have an account?{" "}
            <Link
              href="/login"
              className="text-secondary/70 hover:text-secondary transition-colors"
            >
              Log in
            </Link>
          </p>
        </div>
      </main>

      {/* Free tier info */}
      <footer className="border-t border-border-dim py-8 px-6">
        <div className="max-w-md mx-auto">
          <div className="grid grid-cols-3 gap-4 text-center">
            {[
              { value: "50", label: "Free leads/mo" },
              { value: "∞", label: "Saved searches" },
              { value: "$0", label: "Forever free tier" },
            ].map((stat) => (
              <div key={stat.label}>
                <p className="font-mono text-xl font-bold text-text-primary mb-1">
                  {stat.value}
                </p>
                <p className="font-mono text-[12px] uppercase tracking-[0.2em] text-text-dim">
                  {stat.label}
                </p>
              </div>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
