import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import SessionProvider from "./components/auth/SessionProvider";
import { PipelineProvider } from "./components/hunt/PipelineContext";
import BillingProvider from "./components/billing/BillingProvider";
import { ToastProvider } from "./components/ui/Toast";

export const metadata: Metadata = {
  title: "Hunt — AI-Powered B2B Lead Discovery Platform",
  description:
    "Find and qualify your perfect B2B leads in minutes, not weeks. AI-powered discovery, scoring, and sales briefs. Start free.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-void text-text-primary font-mono antialiased">
        <SessionProvider>
          <Suspense>
            <BillingProvider>
              <PipelineProvider>
                <ToastProvider>{children}</ToastProvider>
              </PipelineProvider>
            </BillingProvider>
          </Suspense>
        </SessionProvider>
      </body>
    </html>
  );
}
