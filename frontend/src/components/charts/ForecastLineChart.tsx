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
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2b4e" />
        <XAxis dataKey="day" tick={{ fill: "#64748b", fontSize: 11 }} />
        <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
        <Tooltip contentStyle={{ background: "#17162a", border: "1px solid #2d2b4e", borderRadius: 8 }} />
        <Legend />
        <Line type="monotone" dataKey="likes"    stroke="#6366f1" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="shares"   stroke="#06b6d4" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="comments" stroke="#8b5cf6" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="reach"    stroke="#f59e0b" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
