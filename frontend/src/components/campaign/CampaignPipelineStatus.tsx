"use client";

import { Check, CircleAlert, Clock3, Loader2 } from "lucide-react";
import { clsx } from "clsx";
import { ProvenanceBadge } from "@/components/ui/ProvenanceBadge";

export type PipelineStageState = "complete" | "active" | "pending" | "failed" | "unavailable";

export type PipelineStage = {
  label: string;
  state: PipelineStageState;
  note?: string;
};

const icons = {
  complete: Check,
  active: Loader2,
  pending: Clock3,
  failed: CircleAlert,
  unavailable: CircleAlert,
};

export function CampaignPipelineStatus({ stages }: { stages: PipelineStage[] }) {
  return (
    <section aria-label="Campaign pipeline status" className="glass rounded-2xl border border-surface-border p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">Pipeline</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-800">Campaign learning loop</h2>
        </div>
        <ProvenanceBadge value={stages.some((stage) => stage.state === "active") ? "PENDING" : "UNKNOWN"} />
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {stages.map((stage) => {
          const Icon = icons[stage.state];
          return (
            <div key={stage.label} className="flex items-start gap-3 rounded-xl border border-surface-border bg-white/70 p-3">
              <span
                className={clsx(
                  "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                  stage.state === "complete" && "bg-emerald-100 text-emerald-700",
                  stage.state === "active" && "bg-sky-100 text-sky-700",
                  stage.state === "pending" && "bg-amber-100 text-amber-700",
                  stage.state === "failed" && "bg-rose-100 text-rose-700",
                  stage.state === "unavailable" && "bg-slate-100 text-slate-500",
                )}
              >
                <Icon size={15} className={stage.state === "active" ? "animate-spin" : undefined} />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-slate-800">{stage.label}</span>
                <span className="mt-0.5 block text-xs capitalize text-slate-500">{stage.note || stage.state}</span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
