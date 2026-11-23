"use client";

import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { api, DashboardSummary } from "@/lib/api";

const SLICES = [
  { key: "sentiment_positive", name: "Positive Mention", color: "#10b981" },
  { key: "sentiment_neutral",  name: "Neutral Mention",  color: "#f59e0b" },
  { key: "sentiment_negative", name: "Negative Mention", color: "#ef4444" },
] as const;

/** Sentiment mix of every comment that has been analysed, as stored labels —
 *  the caller renders no numbers until at least one comment exists. */
export function InsightsPieChart() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.analytics.dashboard().then(setSummary).catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <div className="h-[240px] flex items-center justify-center text-xs text-slate-500">
        Could not load sentiment insights.
      </div>
    );
  }

  if (!summary) {
    return <div className="h-[240px] shimmer rounded-xl" />;
  }

  const total = summary.sentiment_total;
  if (total === 0) {
    return (
      <div className="h-[240px] flex flex-col items-center justify-center gap-1 text-center px-6">
        <p className="text-sm text-slate-600">No analysed comments yet</p>
        <p className="text-xs text-slate-500">
          The sentiment split appears here once comments have been analysed.
        </p>
      </div>
    );
  }

  const data = SLICES.map((slice) => ({
    name: slice.name,
    count: summary[slice.key],
    pct: (summary[slice.key] / total) * 100,
    color: slice.color,
  }));

  return (
    <>
      <div className="h-[200px] mb-4">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%" cy="50%"
              innerRadius={60} outerRadius={80}
              paddingAngle={5}
              dataKey="count"
              stroke="none"
            >
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              itemStyle={{ color: '#1e293b', fontWeight: 600, fontSize: '14px' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="space-y-3">
        {data.map((d) => (
          <div key={d.name} className="flex items-center justify-between text-sm p-2 rounded-lg hover:bg-slate-50 transition-colors">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full shadow-sm" style={{ backgroundColor: d.color }}></div>
              <span className="text-slate-700 font-medium">{d.name}</span>
            </div>
            <span className="font-bold text-slate-900">{d.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-slate-400 font-mono pt-2">{total} analysed comments</p>
    </>
  );
}
