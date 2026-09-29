"use client";

import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
} from "recharts";
import type { PosterEvaluation } from "@/lib/api";

export function PosterRadarChart({ eval_ }: { eval_: PosterEvaluation }) {
  const radarData = [
    { dim: "Readability", score: eval_.readability_score },
    { dim: "Layout",      score: eval_.layout_score },
    { dim: "Branding",    score: eval_.branding_score },
    { dim: "Contrast",    score: eval_.contrast_score },
    { dim: "CTA",         score: eval_.cta_score },
    { dim: "Visual",      score: eval_.visual_appeal_score },
  ];

  return (
    <ResponsiveContainer width="100%" height={220}>
      <RadarChart data={radarData}>
        <PolarGrid stroke="#e2e8f0" />
        <PolarAngleAxis dataKey="dim" tick={{ fill: "#64748b", fontSize: 11 }} />
        <Radar dataKey="score" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
