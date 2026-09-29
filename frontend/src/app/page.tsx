import Link from "next/link";
import { Megaphone, Plus, TrendingUp, Zap, Target, ImageIcon, Users, Bot, Twitter, Facebook, Instagram, ChevronRight, ChevronLeft } from "lucide-react";
import dynamic from "next/dynamic";
import { DashboardStats } from "@/components/dashboard/DashboardStats";
import { RecentCampaigns } from "@/components/dashboard/RecentCampaigns";
import { GeneratedPostersCarousel } from "@/components/dashboard/GeneratedPostersCarousel";

// Dynamically import the heavy Recharts charts — SSR disabled, shown only client-side
const EngagementChart = dynamic(
  () => import("@/components/charts/EngagementChart").then((m) => m.EngagementChart),
  { ssr: false, loading: () => <div className="h-[240px] shimmer rounded-xl" /> }
);

const InsightsPieChart = dynamic(
  () => import("@/components/charts/InsightsPieChart").then((m) => m.InsightsPieChart),
  { ssr: false, loading: () => <div className="h-[200px] shimmer rounded-xl" /> }
);

const QUICK_ACTIONS = [
  { href: "/poster",       label: "Generate Poster",     icon: ImageIcon,  bg: "bg-cyan-50",     text: "text-cyan-600" },
  { href: "#",             label: "Generate Ad Copy",    icon: Megaphone,  bg: "bg-blue-50",     text: "text-blue-600" },
  { href: "/leads",        label: "Analyze Sentiment",   icon: Users,      bg: "bg-violet-50",   text: "text-violet-600" },
  { href: "/leads",        label: "Score Lead",          icon: Target,     bg: "bg-rose-50",     text: "text-rose-600" },
  { href: "/analytics",    label: "Run Forecast",        icon: TrendingUp, bg: "bg-emerald-50",  text: "text-emerald-600" },
  { href: "/optimization", label: "Optimize Campaign",   icon: Zap,        bg: "bg-amber-50",    text: "text-amber-600" },
];

const INSIGHTS_DATA = [
  { name: 'Positive', value: 65, color: '#10b981' },
  { name: 'Neutral', value: 25, color: '#f59e0b' },
  { name: 'Negative', value: 10, color: '#ef4444' },
];

export default function DashboardPage() {

  return (
    <div className="space-y-8 animate-fade-in-up pb-12">
      {/* ── Hero greeting + date ────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 mb-2">
        <div>
          <p className="text-sm font-medium text-slate-500 mb-1" suppressHydrationWarning>
            Good morning 👋 · {new Date().toLocaleDateString('en-GB', {
              weekday: 'long', day: 'numeric', month: 'short', year: 'numeric'
            })}
          </p>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            NexMarket AI is ready.
          </h1>
        </div>
      </div>

      {/* ── Hero banner ────────────────────────────────────────── */}
      <div className="relative overflow-hidden bg-gradient-to-r from-blue-600 to-violet-600 rounded-3xl p-8 sm:p-12 text-white shadow-xl">
        <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-8">
          <div className="space-y-4 max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/20 backdrop-blur-sm border border-white/30 text-sm font-medium">
              <Bot size={16} />
              <span>NexMarket AI Assistant</span>
            </div>
            <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight">
              From Idea to Impact with AI
            </h1>
            <p className="text-blue-100 text-lg md:text-xl max-w-xl">
              Automate your marketing workflow, generate stunning visuals, and analyze engagement in real-time.
            </p>
            <div className="flex gap-4 pt-4">
              <Link href="/campaign/new" className="bg-white text-blue-600 px-6 py-3 rounded-xl font-bold flex items-center gap-2 hover:bg-blue-50 transition-colors">
                <Plus size={18} /> New Campaign
              </Link>
            </div>
          </div>
          <div className="hidden md:flex gap-6 opacity-80">
            <div className="w-16 h-16 rounded-2xl bg-white/10 backdrop-blur-md flex items-center justify-center border border-white/20 animate-pulse">
              <Twitter size={32} />
            </div>
            <div className="w-16 h-16 rounded-2xl bg-white/10 backdrop-blur-md flex items-center justify-center border border-white/20 animate-pulse delay-75">
              <Facebook size={32} />
            </div>
            <div className="w-16 h-16 rounded-2xl bg-white/10 backdrop-blur-md flex items-center justify-center border border-white/20 animate-pulse delay-150">
              <Instagram size={32} />
            </div>
          </div>
        </div>
        {/* Decorative background elements */}
        <div className="absolute -top-24 -right-24 w-96 h-96 bg-white/10 rounded-full blur-3xl"></div>
        <div className="absolute -bottom-24 -left-24 w-72 h-72 bg-violet-400/20 rounded-full blur-3xl"></div>
      </div>

      {/* ── KPI Cards ───────────────────────────────────────────────────── */}
      <DashboardStats />

      {/* ── Two column: Recent Campaigns & Generated Posters ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass rounded-2xl p-6 shadow-sm border border-slate-200 bg-white">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
              <Megaphone size={16} className="text-blue-500" /> Recent Campaigns
            </h2>
            <Link href="/campaign" className="text-xs text-blue-600 font-medium hover:underline">View all</Link>
          </div>
          <RecentCampaigns />
        </div>
        
        <div className="glass rounded-2xl p-6 shadow-sm border border-slate-200 bg-white">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
              <ImageIcon size={16} className="text-cyan-500" /> Generated Posters
            </h2>
          </div>
          <GeneratedPostersCarousel />
        </div>
      </div>

      {/* ── Two column: Engagement Forecast & AI Insights ────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass rounded-2xl p-6 shadow-sm border border-slate-200 bg-white">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-base font-bold text-slate-800 flex items-center gap-2">
                <TrendingUp size={18} className="text-emerald-500" /> Engagement Forecast
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Predictive analytics and historical performance for the next 14 days
              </p>
            </div>
            <Link href="/analytics" className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1">
              Full analytics →
            </Link>
          </div>
          <EngagementChart />
        </div>
        
        <div className="glass rounded-2xl p-6 shadow-sm border border-slate-200 bg-white">
          <h2 className="text-sm font-bold text-slate-800 mb-4 uppercase tracking-wider flex items-center gap-2">
             <Bot size={16} className="text-violet-500" /> AI Insights
          </h2>
          <InsightsPieChart />
          <div className="space-y-3 mt-4">
            {INSIGHTS_DATA.map(d => (
              <div key={d.name} className="flex items-center justify-between text-sm p-2 rounded-lg hover:bg-slate-50 transition-colors">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full shadow-sm" style={{ backgroundColor: d.color }}></div>
                  <span className="text-slate-700 font-medium">{d.name} Mention</span>
                </div>
                <span className="font-bold text-slate-900">{d.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Quick Actions Bar ────────────────── */}
      <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 mt-4">
        <h2 className="text-sm font-bold text-slate-800 mb-4 uppercase tracking-wider flex items-center gap-2">
          <Zap size={16} className="text-amber-500" /> Quick Actions
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {QUICK_ACTIONS.map(({ href, label, icon: Icon, bg, text }) => (
            <Link
              key={label}
              href={href}
              className={`border border-slate-100 rounded-xl p-4 flex flex-col items-center justify-center gap-3 hover:border-blue-300 hover:shadow-md transition-all group ${bg}`}
            >
              <div className={`w-10 h-10 rounded-full bg-white/80 shadow-sm flex items-center justify-center flex-shrink-0`}>
                <Icon size={18} className={text} />
              </div>
              <span className={`text-xs font-bold text-center ${text}`}>
                {label}
              </span>
            </Link>
          ))}
        </div>
      </div>

    </div>
  );
}
