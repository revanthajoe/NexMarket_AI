/**
 * Dashboard — Server Component shell.
 * Interactive parts are isolated into small "use client" islands:
 *   - DashboardStats (fetches + displays stat cards)
 *   - EngagementChart (Recharts, dynamic import)
 * The header and quick-action links are pure Server Component HTML.
 */
import Link from "next/link";
import { Megaphone, Image as ImageIcon, TrendingUp, Plus } from "lucide-react";
import dynamic from "next/dynamic";
import { DashboardStats } from "@/components/dashboard/DashboardStats";

// Dynamically import the heavy Recharts chart — SSR disabled, shown only client-side
const EngagementChart = dynamic(
  () => import("@/components/charts/EngagementChart").then((m) => m.EngagementChart),
  { ssr: false, loading: () => <div className="h-[220px] shimmer rounded-xl" /> }
);

const QUICK_ACTIONS = [
  { href: "/campaign/new", label: "Launch Campaign",  icon: Megaphone,  desc: "Create and deploy a new AI campaign" },
  { href: "/poster",       label: "Generate Poster",  icon: ImageIcon,  desc: "AI-generated marketing visuals" },
  { href: "/analytics",    label: "View Analytics",   icon: TrendingUp, desc: "LSTM forecasts and performance data" },
];

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
            <h1 className="text-3xl font-bold text-slate-900">
            <span className="gradient-text">NexMarket AI</span>
          </h1>
          <p className="text-slate-600 mt-1 text-sm">
            AI-powered marketing automation — all pipelines in one place
          </p>
        </div>
        <Link
          href="/campaign/new"
          className="btn-brand px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"
        >
          <Plus size={16} /> New Campaign
        </Link>
      </div>

      {/* Stats Grid — client island (fetches /analytics/dashboard) */}
      <DashboardStats />

      {/* Engagement Chart — client island (Recharts) */}
      <div className="glass rounded-2xl p-6 border border-surface-border">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-800">Engagement Overview</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              14-day campaign performance, aggregated across all campaigns
            </p>
          </div>
        </div>
        <EngagementChart />
      </div>

      {/* Quick Actions — pure Server Component (static links, no JS needed) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {QUICK_ACTIONS.map(({ href, label, icon: Icon, desc }) => (
          <Link
            key={href}
            href={href}
            className="glass rounded-xl p-5 border border-surface-border hover:border-brand-500/50
                       transition-all duration-200 hover:shadow-card-hover group"
          >
            <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center mb-3
                            group-hover:bg-brand-500/20 transition-colors">
              <Icon size={18} className="text-brand-400" />
            </div>
            <p className="text-sm font-semibold text-slate-800">{label}</p>
            <p className="text-xs text-slate-500 mt-1">{desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
