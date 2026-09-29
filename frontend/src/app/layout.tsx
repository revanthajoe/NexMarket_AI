import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/ui/Sidebar";
import { ToasterProvider } from "@/components/ui/ToasterProvider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "NexMarket AI — AI Marketing Automation Platform",
  description:
    "Generate posters, ad copy, and automatically post campaigns across all platforms with AI-powered optimization.",
  keywords: "AI marketing, campaign automation, social media posting, LSTM forecasting",
  icons: {
    icon: "/favicon.svg",
  },
};

import { ThemeProvider } from "@/components/ui/ThemeProvider";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`} suppressHydrationWarning>
      <body className="bg-surface text-slate-800 flex h-screen overflow-hidden antialiased font-sans dark:bg-slate-900 dark:text-slate-100">
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
          <Sidebar />
          <main className="flex-1 overflow-y-auto bg-surface dark:bg-slate-900">
            <div className="max-w-7xl mx-auto px-6 py-8 animate-fade-in">
              {children}
            </div>
          </main>
          <ToasterProvider />
        </ThemeProvider>
      </body>
    </html>
  );
}
