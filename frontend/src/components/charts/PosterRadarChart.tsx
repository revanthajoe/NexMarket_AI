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
        <PolarGrid stroke="#2d2b4e" />
        <PolarAngleAxis dataKey="dim" tick={{ fill: "#94a3b8", fontSize: 11 }} />
        <Radar dataKey="score" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
