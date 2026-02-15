"use client";

import Link from "next/link";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    href?: string;
    onClick?: () => void;
  };
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="bg-surface-2 border border-border-dim rounded-xl p-12 text-center">
      {icon && <div className="text-4xl mb-4">{icon}</div>}
      <p className="font-mono text-sm text-text-primary mb-2">{title}</p>
      {description && (
        <p className="font-mono text-xs text-text-dim mb-6 max-w-sm mx-auto">
          {description}
        </p>
      )}
      {action && (
        action.href ? (
          <Link
            href={action.href}
            className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors"
          >
            {action.label}
          </Link>
        ) : (
          <button
            onClick={action.onClick}
            className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors cursor-pointer"
          >
            {action.label}
          </button>
        )
      )}
    </div>
  );
}
