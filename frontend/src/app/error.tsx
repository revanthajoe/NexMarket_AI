"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("App Router Error:", error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6 animate-fade-in">
      <div className="w-14 h-14 rounded-2xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600 mb-4 shadow-sm">
        <AlertTriangle size={28} />
      </div>
      <h2 className="text-xl font-bold text-slate-900 tracking-tight">Something went wrong</h2>
      <p className="text-slate-500 text-sm max-w-md mt-2 leading-relaxed">
        {error.message || "An unexpected error occurred while rendering this page."}
      </p>
      {error.digest && (
        <p className="text-[11px] font-mono text-slate-400 mt-2 bg-slate-100 px-2 py-1 rounded">
          Digest: {error.digest}
        </p>
      )}
      <div className="flex items-center gap-3 mt-6">
        <button
          onClick={() => reset()}
          className="btn-brand px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"
        >
          <RotateCcw size={15} />
          Try Again
        </button>
        <button
          onClick={() => window.location.reload()}
          className="px-5 py-2.5 rounded-xl text-sm font-semibold border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors"
        >
          Reload Page
        </button>
      </div>
    </div>
  );
}
