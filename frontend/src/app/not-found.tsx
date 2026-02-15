import Link from "next/link";

export const dynamic = "force-dynamic";

export default function NotFound() {
  return (
    <div className="min-h-dvh bg-void flex items-center justify-center p-6">
      <div className="bg-surface-2 border border-border-dim rounded-xl p-12 text-center max-w-md w-full">
        <p className="font-mono text-4xl font-bold text-text-primary mb-4">404</p>
        <p className="font-mono text-sm text-text-primary mb-2">Page not found</p>
        <p className="font-mono text-xs text-text-dim mb-6 max-w-sm mx-auto">
          The page you&apos;re looking for doesn&apos;t exist or was moved.
        </p>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
