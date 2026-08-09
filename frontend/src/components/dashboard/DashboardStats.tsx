"use client";

import { useEffect, useState } from "react";
import {
  Megaphone, Send, TrendingUp,
  Target, Users, ArrowUpRight, Loader2, Zap,
} from "lucide-react";
import { api, DashboardSummary } from "@/lib/api";

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
        <div className="p-2.5 rounded-lg bg-current/10">
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

export function DashboardStats() {
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
        { label: "Total Campaigns",  value: summary.total_campaigns,              icon: Megaphone, color: "brand"   },
        { label: "Active Campaigns", value: summary.active_campaigns,             icon: Zap,       color: "emerald" },
        { label: "Posts Published",  value: summary.successful_posts,             icon: Send,      color: "cyan",
          sub: `${summary.total_posts} total` },
        { label: "Avg Engagement",   value: `${summary.avg_engagement_rate}%`,    icon: TrendingUp, color: "amber"  },
        { label: "Total Leads",      value: summary.total_leads,                  icon: Users,     color: "brand"   },
        { label: "Hot Leads 🔥",     value: summary.hot_leads,                    icon: Target,    color: "rose"    },
      ]
    : [];

  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="shimmer h-28 rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
      {stats.map((s, i) => (
        <StatCard key={i} {...s} />
      ))}
    </div>
  );
}
