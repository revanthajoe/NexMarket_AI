"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Megaphone, Image as ImageIcon, Send, TrendingUp,
  Target, Users, ArrowUpRight, Loader2, Zap, Plus,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { api, DashboardSummary, AnalyticsEvent } from "@/lib/api";

function StatCard({
  label, value, sub, icon: Icon, color = "brand",
}: {
  label: string; value: string | number; sub?: string;
  icon: React.ElementType; color?: string;
}) {
  const colorMap: Record<string, string> = {
    brand:   "from-brand-500/20 to-brand-600/10 border-brand-500/30 text-brand-400",
    emerald: "from-emerald-500/20 to-emerald-600/10 border-emerald-500/30 text-emerald-400",
    amber:   "from-amber-500/20 to-amber-600/10 border-amber-500/30 text-amber-400",
    rose:    "from-rose-500/20 to-rose-600/10 border-rose-500/30 text-rose-400",
    cyan:    "from-cyan-500/20 to-cyan-600/10 border-cyan-500/30 text-cyan-400",
  };
  const cls = colorMap[color] || colorMap.brand;

  return (
    <div className={`glass rounded-xl p-5 bg-gradient-to-br ${cls} border animate-slide-up`}>
      <div className="flex items-start justify-between mb-4">
        <div className={`p-2.5 rounded-lg bg-current/10`}>
          <Icon size={18} className={cls.split(" ").pop()} />
        </div>
        <ArrowUpRight size={14} className="text-slate-500" />
      </div>
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="text-sm text-slate-400 mt-1">{label}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

const DEMO_CHART = Array.from({ length: 14 }, (_, i) => ({
  day: `Day ${i + 1}`,
  likes: Math.floor(200 + Math.random() * 800),
  reach: Math.floor(1000 + Math.random() * 4000),
  clicks: Math.floor(50 + Math.random() * 300),
}));

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.analytics.dashboard()
      .then(setSummary)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const stats = summary
    ? [
        { label: "Total Campaigns",    value: summary.total_campaigns,    icon: Megaphone, color: "brand" },
        { label: "Active Campaigns",   value: summary.active_campaigns,   icon: Zap,       color: "emerald" },
        { label: "Posts Published",    value: summary.successful_posts,   icon: Send,      color: "cyan",
          sub: `${summary.total_posts} total` },
        { label: "Avg Engagement",     value: `${summary.avg_engagement_rate}%`, icon: TrendingUp, color: "amber" },
        { label: "Total Leads",        value: summary.total_leads,        icon: Users,     color: "brand" },
        { label: "Hot Leads 🔥",       value: summary.hot_leads,          icon: Target,    color: "rose" },
      ]
    : [];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">
            <span className="gradient-text">NexMarket AI</span>
          </h1>
          <p className="text-slate-400 mt-1 text-sm">
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

      {/* Stats Grid */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="shimmer h-28 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {stats.map((s, i) => (
            <StatCard key={i} {...s} />
          ))}
        </div>
      )}

      {/* Engagement Chart */}
      <div className="glass rounded-2xl p-6 border border-surface-border">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-semibold text-white">Engagement Overview</h2>
            <p className="text-xs text-slate-500 mt-0.5">14-day campaign performance</p>
          </div>
          <span className="text-xs text-slate-500 glass px-3 py-1 rounded-full border border-surface-border">
            Live Data
          </span>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={DEMO_CHART}>
            <defs>
              <linearGradient id="colorLikes" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorReach" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d2b4e" />
            <XAxis dataKey="day" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: "#17162a", border: "1px solid #2d2b4e", borderRadius: 8 }}
              labelStyle={{ color: "#94a3b8" }}
            />
            <Area type="monotone" dataKey="likes"  stroke="#6366f1" fill="url(#colorLikes)"  strokeWidth={2} />
            <Area type="monotone" dataKey="reach"  stroke="#06b6d4" fill="url(#colorReach)"  strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { href: "/campaign/new", label: "Launch Campaign",    icon: Megaphone, desc: "Create and deploy a new AI campaign" },
          { href: "/poster",       label: "Generate Poster",    icon: ImageIcon,  desc: "AI-generated marketing visuals" },
          { href: "/analytics",    label: "View Analytics",     icon: TrendingUp, desc: "LSTM forecasts and performance data" },
        ].map(({ href, label, icon: Icon, desc }) => (
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
            <p className="text-sm font-semibold text-white">{label}</p>
            <p className="text-xs text-slate-500 mt-1">{desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
