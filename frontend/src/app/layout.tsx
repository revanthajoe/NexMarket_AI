import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/ui/Sidebar";
import { Toaster } from "react-hot-toast";

export const metadata: Metadata = {
  title: "NexMarket AI — AI Marketing Automation Platform",
  description:
    "Generate posters, ad copy, and automatically post campaigns across all platforms with AI-powered optimization.",
  keywords: "AI marketing, campaign automation, social media posting, LSTM forecasting",
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
      </head>
      <body className="bg-surface text-slate-200 flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-surface">
          <div className="max-w-7xl mx-auto p-6 animate-fade-in">
            {children}
          </div>
        </main>
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#17162a",
              color: "#e2e8f0",
              border: "1px solid #2d2b4e",
            },
          }}
        />
      </body>
    </html>
  );
}
