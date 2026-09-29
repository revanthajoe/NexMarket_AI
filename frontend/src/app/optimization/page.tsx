"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Target, Zap } from "lucide-react";
import { api, Campaign, Optimization } from "@/lib/api";

export default function OptimizationPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<string>("");
  const [budget, setBudget] = useState<number>(1000);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Optimization | null>(null);

  useEffect(() => {
    api.campaigns.list().then((res) => {
      setCampaigns(res);
      if (res.length > 0) setSelectedCampaign(res[0].id);
    }).catch(() => {});
  }, []);

  const handleOptimize = async () => {
    if (!selectedCampaign) return;
    setLoading(true);
    try {
      const opt = await api.optimize.run(selectedCampaign, budget);
      setResult(opt);
      toast.success("Strategy optimized successfully");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to run optimization");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
            <Target size={18} className="text-blue-600" />
          </div>
          Strategy Optimizer
        </h1>
        <p className="text-slate-500 mt-1.5 text-sm">
          Multi-Armed Bandit (Thompson Sampling) budget and platform allocation
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white border border-slate-200 rounded-2xl p-6 animate-fade-in-up">
          <h2 className="text-base font-semibold text-slate-800 mb-4">Run Optimization</h2>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="opt-campaign" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Select Campaign
              </label>
              <select
                id="opt-campaign"
                name="opt-campaign"
                className="input-dark"
                value={selectedCampaign}
                onChange={(e) => setSelectedCampaign(e.target.value)}
              >
                {campaigns.length === 0 && <option value="">No campaigns available</option>}
                {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="opt-budget" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Allocated Budget (\$)
              </label>
              <input
                id="opt-budget"
                name="opt-budget"
                type="number"
                min={0}
                className="input-dark"
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
              />
            </div>
            <button
              onClick={handleOptimize}
              disabled={loading || !selectedCampaign}
              className="btn-brand w-full py-2.5 rounded-xl font-semibold flex items-center justify-center gap-2 mt-2"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
              Run Thompson Sampling
            </button>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl p-6 animate-fade-in-up delay-100">
          <h2 className="text-base font-semibold text-slate-800 mb-4">Optimization Results</h2>
          {!result ? (
            <div className="h-48 flex flex-col items-center justify-center text-slate-400 text-sm border-2 border-dashed border-slate-200 rounded-xl gap-2">
              <Target size={24} className="text-slate-300" />
              Run optimizer to view AI recommendations
            </div>
          ) : (
            <div className="space-y-5 animate-scale-up">
              <div className="text-xs uppercase tracking-wide text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full inline-block font-semibold">
                {result.source_type || "UNKNOWN"} · {result.algorithm || "Thompson Sampling"}
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                  <div className="text-xs text-blue-600 uppercase tracking-wide mb-1.5 font-semibold">Best Platform</div>
                  <div className="text-xl font-bold text-slate-900 capitalize">{result.recommended_platform}</div>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1.5 font-semibold">AI Confidence</div>
                  <div className="text-xl font-bold text-slate-900">{(result.confidence * 100).toFixed(1)}%</div>
                </div>
              </div>

              {result.reasoning && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Reasoning</h3>
                  <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-200">
                    {result.reasoning}
                  </p>
                </div>
              )}

              {result.platform_scores && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                    Platform Scores (Thompson Samples)
                  </h3>
                  <div className="space-y-3">
                    {Object.entries(result.platform_scores).map(([p, score], i) => (
                      <div key={p} className="animate-fade-in-up" style={{ animationDelay: `${i * 80}ms` }}>
                        <div className="flex justify-between text-sm mb-1.5">
                          <span className="text-slate-700 capitalize font-medium">{p}</span>
                          <span className="text-blue-600 font-mono text-xs">{score.toFixed(3)}</span>
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full transition-all duration-1000"
                            style={{ width: `${Math.min(100, Math.max(0, score * 100))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="text-[10px] text-slate-400 font-mono pt-1 border-t border-slate-100">
                Policy: {result.policy_version || "—"} · Algorithm: {result.algorithm || "Thompson Sampling"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}