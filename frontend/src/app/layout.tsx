import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/ui/Sidebar";
import { ToasterProvider } from "@/components/ui/ToasterProvider";

export const metadata: Metadata = {
  title: "NexMarket AI — AI Marketing Automation Platform",
  description:
    "Generate posters, ad copy, and automatically post campaigns across all platforms with AI-powered optimization.",
  keywords: "AI marketing, campaign automation, social media posting, LSTM forecasting",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
        />
      </head>
      <body className="bg-surface text-slate-700 flex h-screen overflow-hidden ambient-background">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-surface/80">
          <div className="max-w-7xl mx-auto p-6 animate-fade-in">
            {children}
          </div>
        </main>
        <ToasterProvider />
      </body>
    </html>
  );
}

