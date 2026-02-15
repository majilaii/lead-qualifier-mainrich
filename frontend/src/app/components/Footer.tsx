export default function Footer() {
  return (
    <footer className="bg-void border-t border-border-dim py-16 px-6">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-12 mb-12">
          {/* Brand */}
          <div className="md:col-span-2">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-secondary text-lg font-bold">
                &#x25C8;
              </span>
              <span className="text-text-primary text-sm font-semibold tracking-[0.15em] uppercase">
                Hunt
              </span>
            </div>
            <p className="text-text-muted text-xs leading-relaxed max-w-sm font-sans">
              AI-Powered B2B Lead Discovery & Qualification Pipeline. Built for
              any B2B seller. Designed to scale.
            </p>
            <div className="mt-4 font-mono text-[12px] tracking-[0.2em] text-text-dim uppercase">
              Powered by Hunt AI
            </div>
          </div>

          {/* Links */}
          <div>
            <h4 className="text-[12px] uppercase tracking-[0.3em] text-secondary/50 mb-4">
              Product
            </h4>
            <ul className="space-y-2">
              {[
                { label: "How It Works", href: "#how-it-works" },
                { label: "Pipeline", href: "#pipeline" },
                { label: "Features", href: "#features" },
                { label: "Pricing", href: "#pricing" },
              ].map((item) => (
                <li key={item.label}>
                  <a
                    href={item.href}
                    className="text-text-muted text-xs hover:text-text-primary transition-colors"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* More */}
          <div>
            <h4 className="text-[12px] uppercase tracking-[0.3em] text-secondary/50 mb-4">
              Company
            </h4>
            <ul className="space-y-2">
              {[
                { label: "Sign Up Free", href: "/signup" },
                { label: "Log In", href: "/login" },
                { label: "Contact", href: "#" },
                { label: "Privacy Policy", href: "#" },
                { label: "Terms of Service", href: "#" },
              ].map((item) => (
                <li key={item.label}>
                  <a
                    href={item.href}
                    className="text-text-muted text-xs hover:text-text-primary transition-colors"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Bottom */}
        <div className="border-t border-border-dim pt-6 flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="font-mono text-[12px] tracking-[0.2em] text-text-dim uppercase">
            &copy; {new Date().getFullYear()} Hunt. All rights
            reserved.
          </p>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-secondary/60 animate-pulse" />
            <span className="font-mono text-[12px] tracking-[0.2em] text-text-muted uppercase">
              System Online
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
