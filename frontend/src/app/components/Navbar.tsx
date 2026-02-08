"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed top-0 left-0 w-full z-50 transition-all duration-300 ${
        scrolled
          ? "bg-void/90 backdrop-blur-md border-b border-border-dim"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <span className="text-secondary text-lg font-bold tracking-tight">
            &#x25C8;
          </span>
          <span className="text-text-primary text-sm font-semibold tracking-[0.15em] uppercase">
            The Magnet Hunter
          </span>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-8">
          <a
            href="#how-it-works"
            className="text-text-muted text-xs uppercase tracking-[0.2em] hover:text-text-primary transition-colors duration-200"
          >
            How It Works
          </a>
          <a
            href="#pipeline"
            className="text-text-muted text-xs uppercase tracking-[0.2em] hover:text-text-primary transition-colors duration-200"
          >
            Pipeline
          </a>
          <a
            href="#features"
            className="text-text-muted text-xs uppercase tracking-[0.2em] hover:text-text-primary transition-colors duration-200"
          >
            Features
          </a>
          <a
            href="#cta"
            className="inline-flex items-center gap-2 bg-text-primary text-void text-xs font-semibold uppercase tracking-[0.15em] px-5 py-2.5 rounded hover:bg-white/85 transition-colors duration-200"
          >
            Get Started
            <span className="text-[10px]">&#x2192;</span>
          </a>
        </nav>

        {/* Mobile Menu Button */}
        <button
          className="md:hidden text-text-secondary hover:text-text-primary transition-colors p-2"
          aria-label="Menu"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M3 5h14M3 10h14M3 15h14" />
          </svg>
        </button>
      </div>
    </header>
  );
}
