"use client";

export function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "w-4 h-4", md: "w-6 h-6", lg: "w-8 h-8" };
  return (
    <div
      className={`${sizes[size]} border-2 border-surface-3 border-t-secondary rounded-full animate-spin`}
      role="status"
      aria-label="Loading"
    />
  );
}
