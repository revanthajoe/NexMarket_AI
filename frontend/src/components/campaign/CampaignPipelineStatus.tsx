"use client";

import { Check, CircleAlert, Clock3, Loader2 } from "lucide-react";
import { clsx } from "clsx";

export type PipelineStageState = "complete" | "active" | "pending" | "failed" | "unavailable";

export type PipelineStage = {
  label: string;
  state: PipelineStageState;
  note?: string;
};

const STATE_STYLES = {
  complete:    { dot: "bg-emerald-500", text: "text-slate-800 dark:text-slate-200" },
  active:      { dot: "bg-blue-500",    text: "text-blue-700 dark:text-blue-400 font-semibold" },
  pending:     { dot: "bg-slate-200 dark:bg-slate-700",   text: "text-slate-500 dark:text-slate-400" },
  failed:      { dot: "bg-rose-500",    text: "text-rose-700 dark:text-rose-400 font-semibold" },
  unavailable: { dot: "bg-slate-100 dark:bg-slate-800",   text: "text-slate-400 dark:text-slate-500" },
};

function StageIcon({ state }: { state: PipelineStageState }) {
  if (state === "complete") {
    return (
      <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center relative z-10 ring-4 ring-white dark:ring-slate-900 shadow-sm">
        <Check size={10} className="text-white" strokeWidth={3} />
      </div>
    );
  }
  if (state === "active") {
    return (
      <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center relative z-10 ring-4 ring-white dark:ring-slate-900 shadow-sm">
        <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
      </div>
    );
  }
  if (state === "failed") {
    return (
      <div className="w-5 h-5 rounded-full bg-rose-500 flex items-center justify-center relative z-10 ring-4 ring-white dark:ring-slate-900 shadow-sm">
        <CircleAlert size={10} className="text-white" />
      </div>
    );
  }
  return (
    <div className={clsx(
      "w-5 h-5 rounded-full flex items-center justify-center relative z-10 ring-4 ring-white dark:ring-slate-900",
      state === "pending" ? "bg-slate-200 dark:bg-slate-700" : "bg-slate-100 dark:bg-slate-800"
    )}>
      <div className="w-1.5 h-1.5 rounded-full bg-white dark:bg-slate-400" />
    </div>
  );
}

export function CampaignPipelineStatus({ stages }: { stages: PipelineStage[] }) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm w-full overflow-x-auto">
      <div className="flex items-start min-w-max px-2 py-1">
        {stages.map((stage, idx) => {
          const isLast = idx === stages.length - 1;
          const s = STATE_STYLES[stage.state];
          
          return (
            <div key={stage.label} className="flex items-start">
              {/* Step indicator and label */}
              <div className="flex flex-col items-center w-16 sm:w-20">
                <div className="h-6 flex items-center justify-center">
                  <StageIcon state={stage.state} />
                </div>
                <div className="mt-2 text-center w-full px-0.5">
                  <span className={clsx(
                    "text-[11px] font-medium leading-tight block",
                    s.text
                  )}>
                    {stage.label}
                  </span>
                  {stage.note && (
                    <span className="block text-[9px] text-slate-400 dark:text-slate-500 mt-0.5 leading-tight">
                      {stage.note}
                    </span>
                  )}
                </div>
              </div>
              
              {/* Connector line */}
              {!isLast && (
                <div className="h-6 flex items-center w-6 sm:w-10 flex-shrink-0">
                  <div className={clsx(
                    "w-full h-0.5 rounded-full transition-colors",
                    stage.state === "complete" 
                      ? "bg-emerald-500" 
                      : "bg-slate-200 dark:bg-slate-700"
                  )} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
