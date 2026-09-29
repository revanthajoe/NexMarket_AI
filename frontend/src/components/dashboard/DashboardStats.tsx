"use client";

import { useEffect, useState } from "react";
import {
  Megaphone, Send, TrendingUp,
  Target, Users, ArrowUpRight, Zap,
} from "lucide-react";
import { api, DashboardSummary } from "@/lib/api";

const STAT_CONFIG = [
  {
    key: "total_campaigns" as const,
    label: "Total Campaigns",
    icon: Megaphone,
    color: { bg: "bg-blue-50", icon: "text-blue-600", value: "text-slate-900", border: "border-l-blue-500" },
    format: (v: number) => v.toString(),
  },
  {
    key: "active_campaigns" as const,
    label: "Active Campaigns",
    icon: Zap,
    color: { bg: "bg-emerald-50", icon: "text-emerald-600", value: "text-slate-900", border: "border-l-emerald-500" },
    format: (v: number) => v.toString(),
  },
  {
    key: "successful_posts" as const,
    label: "Posts Published",
    icon: Send,
    color: { bg: "bg-cyan-50", icon: "text-cyan-600", value: "text-slate-900", border: "border-l-cyan-500" },
    format: (v: number) => v.toString(),
  },
  {
    key: "avg_engagement_rate" as const,
    label: "Avg Engagement",
    icon: TrendingUp,
    color: { bg: "bg-amber-50", icon: "text-amber-600", value: "text-slate-900", border: "border-l-amber-500" },
    format: (v: number) => `${v}%`,
  },
  {
    key: "total_leads" as const,
    label: "Total Leads",
    icon: Users,
    color: { bg: "bg-violet-50", icon: "text-violet-600", value: "text-slate-900", border: "border-l-violet-500" },
    format: (v: number) => v.toString(),
  },
  {
    key: "hot_leads" as const,
    label: "Hot Leads",
    icon: Target,
    color: { bg: "bg-rose-50", icon: "text-rose-600", value: "text-slate-900", border: "border-l-rose-500" },
    format: (v: number) => v.toString(),
  },
];

function StatCardSkeleton() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 border-l-4 border-l-slate-200">
      <div className="flex items-start justify-between mb-4">
        <div className="w-9 h-9 rounded-lg shimmer" />
        <div className="w-4 h-4 rounded shimmer" />
      </div>
      <div className="w-16 h-7 rounded shimmer mb-2" />
      <div className="w-28 h-3.5 rounded shimmer" />
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  color: { bg: string; icon: string; value: string; border: string };
}) {
  return (
    <div
      className={`bg-white border border-slate-200 rounded-xl p-5 border-l-4 ${color.border}
                  hover:-translate-y-0.5 hover:shadow-card-hover transition-all duration-150`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className={`w-9 h-9 rounded-lg ${color.bg} flex items-center justify-center`}>
          <Icon size={16} className={color.icon} />
        </div>
        <ArrowUpRight size={13} className="text-slate-300" />
      </div>
      <p className={`text-2xl font-bold tracking-tight ${color.value}`}>{value}</p>
      <p className="text-sm text-slate-500 mt-1">{label}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export function DashboardStats() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.analytics.dashboard()
      .then(setSummary)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <StatCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="bg-rose-50 border border-rose-200 rounded-xl px-5 py-4 text-sm text-rose-700">
        Failed to load dashboard metrics. Check that the backend is running.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
      {STAT_CONFIG.map((cfg, i) => (
        <StatCard
          key={i}
          label={cfg.label}
          value={cfg.format(summary[cfg.key] as number)}
          sub={cfg.key === "successful_posts" ? `${summary.total_posts} total posts` : undefined}
          icon={cfg.icon}
          color={cfg.color}
        />
      ))}
    </div>
  );
}
