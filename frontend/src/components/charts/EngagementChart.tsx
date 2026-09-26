"use client";

import { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { api, EngagementPoint } from "@/lib/api";

interface EngagementChartProps {
  days?: number;
  /** Scope the series to one campaign; omit for platform-wide totals. */
  campaignId?: string;
  /** Bump to force a refetch after an engagement sync. */
  refreshKey?: number;
}

export function EngagementChart({ days = 14, campaignId, refreshKey = 0 }: EngagementChartProps) {
  const [data, setData] = useState<EngagementPoint[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setFailed(false);
    api.analytics.timeseries(days, campaignId)
      .then(d => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [days, campaignId, refreshKey]);

  if (failed) {
    return (
      <div className="h-[220px] flex items-center justify-center text-xs text-slate-500">
        Could not load engagement data.
      </div>
    );
  }

  if (!data) {
    return <div className="h-[220px] shimmer rounded-xl" />;
  }

  if (data.length === 0) {
    return (
      <div className="h-[220px] flex flex-col items-center justify-center gap-1 text-center px-6">
            <p className="text-sm text-slate-600">No ACTUAL engagement data yet</p>
            <p className="text-xs text-slate-500">
          Metrics appear here once published posts start reporting analytics.
        </p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="colorLikes" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b82c4" stopOpacity={0.28} />
            <stop offset="95%" stopColor="#3b82c4" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="colorReach" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#e7bd58" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#e7bd58" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#d7e4ec" />
        <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{ background: "#ffffff", border: "1px solid #d7e4ec", borderRadius: 8 }}
          labelStyle={{ color: "#536b7a" }}
        />
        <Area type="monotone" dataKey="likes" stroke="#3b82c4" fill="url(#colorLikes)" strokeWidth={2} />
        <Area type="monotone" dataKey="reach" stroke="#d4a83d" fill="url(#colorReach)" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
