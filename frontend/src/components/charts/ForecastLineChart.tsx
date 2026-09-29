"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import type { Forecast } from "@/lib/api";

export function ForecastLineChart({ forecast }: { forecast: Forecast }) {
  const chartData = forecast.predicted_likes.map((v, i) => ({
    day: `Day ${i + 1}`,
    likes:    Math.round(v),
    shares:   Math.round(forecast.predicted_shares[i] || 0),
    comments: Math.round(forecast.predicted_comments[i] || 0),
    reach:    Math.round(forecast.predicted_reach[i] || 0),
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="day" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, color: "#1e293b" }} />
        <Legend />
        <Line type="monotone" dataKey="likes"    stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
        <Line type="monotone" dataKey="shares"   stroke="#0ea5e9" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="comments" stroke="#8b5cf6" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="reach"    stroke="#f59e0b" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
