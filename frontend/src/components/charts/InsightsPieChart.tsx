"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

const INSIGHTS_DATA = [
  { name: 'Positive', value: 65, color: '#10b981' },
  { name: 'Neutral', value: 25, color: '#f59e0b' },
  { name: 'Negative', value: 10, color: '#ef4444' },
];

export function InsightsPieChart() {
  return (
    <div className="h-[200px] mb-4">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie 
            data={INSIGHTS_DATA} 
            cx="50%" cy="50%" 
            innerRadius={60} outerRadius={80} 
            paddingAngle={5} 
            dataKey="value"
            stroke="none"
          >
            {INSIGHTS_DATA.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip 
            contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
            itemStyle={{ color: '#1e293b', fontWeight: 600, fontSize: '14px' }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
