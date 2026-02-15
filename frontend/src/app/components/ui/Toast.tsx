"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";

/* ── Types ── */

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastInput {
  title: string;
  description?: string;
  variant?: ToastVariant;
}

interface ToastContextValue {
  toast: (input: ToastInput) => void;
}

/* ── Context ── */

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

/* ── Variant config ── */

const VARIANT_STYLES: Record<ToastVariant, { icon: string; border: string; iconColor: string }> = {
  success: { icon: "✓", border: "border-green-500/30", iconColor: "text-green-400" },
  error: { icon: "✗", border: "border-red-500/30", iconColor: "text-red-400" },
  info: { icon: "ℹ", border: "border-secondary/30", iconColor: "text-secondary" },
};

const DISMISS_MS: Record<ToastVariant, number> = {
  success: 4000,
  error: 8000,
  info: 4000,
};

const MAX_VISIBLE = 3;

/* ── Provider ── */

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback((input: ToastInput) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const variant = input.variant ?? "info";
    setToasts((prev) => [...prev.slice(-(MAX_VISIBLE - 1)), { id, title: input.title, description: input.description, variant }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}

      {/* Toast container — bottom-right */}
      <div
        className="fixed bottom-6 right-6 z-[9999] flex flex-col-reverse gap-2 pointer-events-none"
        aria-live="polite"
        role="status"
      >
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onDismiss={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/* ── Individual toast card ── */

function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const style = VARIANT_STYLES[toast.variant];

  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), DISMISS_MS[toast.variant]);
    return () => clearTimeout(timer);
  }, [toast.id, toast.variant, onDismiss]);

  return (
    <button
      onClick={() => onDismiss(toast.id)}
      className={`pointer-events-auto bg-surface-2 border ${style.border} rounded-xl px-4 py-3 shadow-lg
        animate-toast-in min-w-[260px] max-w-xs text-left cursor-pointer
        hover:bg-surface-3/80 transition-colors`}
    >
      <div className="flex items-start gap-2.5">
        <span className={`${style.iconColor} font-bold text-sm mt-0.5 flex-shrink-0`}>
          {style.icon}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-mono text-xs text-text-primary">{toast.title}</p>
          {toast.description && (
            <p className="font-mono text-[10px] text-text-dim mt-0.5 truncate">
              {toast.description}
            </p>
          )}
        </div>
      </div>
    </button>
  );
}
