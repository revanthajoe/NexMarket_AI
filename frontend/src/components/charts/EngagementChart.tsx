"use client";

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";

// Stable demo data — defined once outside the component so it never changes between renders
const DEMO_CHART = Array.from({ length: 14 }, (_, i) => ({
  day: `Day ${i + 1}`,
  likes: 200 + ((i * 137 + 41) % 800),
  reach: 1000 + ((i * 317 + 83) % 4000),
  clicks: 50 + ((i * 97 + 23) % 300),
}));

export function EngagementChart() {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={DEMO_CHART}>
        <defs>
          <linearGradient id="colorLikes" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="colorReach" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#06b6d4" stopOpacity={0.3} />
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
        <Area type="monotone" dataKey="likes" stroke="#6366f1" fill="url(#colorLikes)" strokeWidth={2} />
        <Area type="monotone" dataKey="reach" stroke="#06b6d4" fill="url(#colorReach)" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
