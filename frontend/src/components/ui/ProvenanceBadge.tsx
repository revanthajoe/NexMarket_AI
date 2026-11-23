"use client";

import { clsx } from "clsx";

export type Provenance =
  | "ACTUAL"
  | "SIMULATED"
  | "PREDICTED"
  | "FORECAST"
  | "RECOMMENDATION"
  | "FALLBACK"
  | "UNKNOWN"
  | "PENDING"
  | "WAITING"
  | "UNAVAILABLE";

const styles: Record<Provenance, string> = {
  ACTUAL: "bg-emerald-50 text-emerald-700 border-emerald-200",
  SIMULATED: "bg-sky-50 text-sky-700 border-sky-200",
  PREDICTED: "bg-blue-50 text-blue-700 border-blue-200",
  FORECAST: "bg-amber-50 text-amber-700 border-amber-200",
  RECOMMENDATION: "bg-yellow-50 text-yellow-800 border-yellow-200",
  FALLBACK: "bg-rose-50 text-rose-700 border-rose-200",
  UNKNOWN: "bg-slate-100 text-slate-600 border-slate-200",
  PENDING: "bg-yellow-50 text-yellow-800 border-yellow-200",
  WAITING: "bg-yellow-50 text-yellow-800 border-yellow-200",
  UNAVAILABLE: "bg-slate-100 text-slate-600 border-slate-200",
};

export function ProvenanceBadge({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const normalized = (value || "UNKNOWN").toUpperCase() as Provenance;
  const label = styles[normalized] ? normalized : "UNKNOWN";

  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-[0.12em]",
        styles[label],
        className,
      )}
    >
      {label}
    </span>
  );
}
