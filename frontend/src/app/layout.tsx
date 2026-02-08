import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Magnet Hunter — AI-Powered B2B Lead Qualification",
  description:
    "From 7.2 billion data points to your perfect lead. AI-powered discovery, crawling, and qualification for hardware B2B companies.",
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
        {children}
      </body>
    </html>
  );
}
