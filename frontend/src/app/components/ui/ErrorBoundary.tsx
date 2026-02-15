"use client";

import { Component, type ReactNode, type ErrorInfo } from "react";

interface ErrorFallbackProps {
  error: Error;
  resetErrorBoundary: () => void;
}

function ErrorFallback({ error, resetErrorBoundary }: ErrorFallbackProps) {
  return (
    <div className="bg-surface-2 border border-red-500/20 rounded-xl p-8 text-center">
      <p className="font-mono text-sm text-red-400 mb-2">Something went wrong</p>
      <p className="font-mono text-xs text-text-dim mb-4 max-w-md mx-auto">
        {error.message}
      </p>
      <button
        onClick={resetErrorBoundary}
        className="font-mono text-[10px] uppercase tracking-[0.15em] text-secondary border border-secondary/30 px-4 py-2 rounded-lg hover:bg-secondary/10 transition-colors cursor-pointer"
      >
        Try Again
      </button>
    </div>
  );
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (props: ErrorFallbackProps) => ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.props.onError?.(error, info);
  }

  resetErrorBoundary = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      const FallbackComponent = this.props.fallback;
      if (FallbackComponent) {
        return FallbackComponent({
          error: this.state.error,
          resetErrorBoundary: this.resetErrorBoundary,
        });
      }
      return (
        <ErrorFallback
          error={this.state.error}
          resetErrorBoundary={this.resetErrorBoundary}
        />
      );
    }
    return this.props.children;
  }
}
