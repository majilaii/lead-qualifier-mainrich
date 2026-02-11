import type { Metadata } from "next";
import "./globals.css";
import SessionProvider from "./components/auth/SessionProvider";
import { HuntProvider } from "./components/hunt/HuntContext";
import BillingProvider from "./components/billing/BillingProvider";

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
          <BillingProvider>
            <HuntProvider>{children}</HuntProvider>
          </BillingProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
