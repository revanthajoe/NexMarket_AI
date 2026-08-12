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
    api.campaigns.list().then(res => {
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
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center">
            <Target size={20} className="text-brand-400" />
          </div>
          Strategy Optimizer
        </h1>
        <p className="text-slate-400 mt-2 text-sm">
          Multi-Armed Bandit (Thompson Sampling) budget and platform allocation
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="glass-dynamic rounded-2xl p-6 animate-fade-in-up">
          <h2 className="text-lg font-semibold text-white mb-4">Run Optimization</h2>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="opt-campaign" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Select Campaign</label>
              <select 
                id="opt-campaign"
                name="opt-campaign"
                className="input-dark" 
                value={selectedCampaign} 
                onChange={e => setSelectedCampaign(e.target.value)}
              >
                {campaigns.length === 0 && <option value="">No campaigns available</option>}
                {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="opt-budget" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Allocated Budget ($)</label>
              <input 
                id="opt-budget"
                name="opt-budget"
                type="number" 
                min={0}
                className="input-dark" 
                value={budget} 
                onChange={e => setBudget(Number(e.target.value))}
              />
            </div>
            <button 
              onClick={handleOptimize} 
              disabled={loading || !selectedCampaign}
              className="btn-brand w-full py-2.5 rounded-xl font-medium flex items-center justify-center gap-2 mt-2"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
              Run Thompson Sampling
            </button>
          </div>
        </div>

        <div className="glass-dynamic rounded-2xl p-6 animate-fade-in-up delay-100">
          <h2 className="text-lg font-semibold text-white mb-4">Optimization Results</h2>
          {!result ? (
            <div className="h-48 flex items-center justify-center text-slate-500 text-sm border border-dashed border-surface-border rounded-xl">
              Run optimizer to view AI recommendations
            </div>
          ) : (
            <div className="space-y-6 animate-scale-up">
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-brand-500/10 border border-brand-500/20 rounded-xl p-4">
                  <div className="text-xs text-brand-400 uppercase tracking-wide mb-1">Recommended Platform</div>
                  <div className="text-xl font-bold text-white capitalize">{result.recommended_platform}</div>
                </div>
                <div className="bg-surface-muted/30 border border-surface-border rounded-xl p-4">
                  <div className="text-xs text-slate-400 uppercase tracking-wide mb-1">AI Confidence</div>
                  <div className="text-xl font-bold text-white">{(result.confidence * 100).toFixed(1)}%</div>
                </div>
              </div>

              {result.reasoning && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Reasoning</h3>
                  <p className="text-sm text-slate-300 leading-relaxed bg-surface-muted/30 p-3 rounded-lg border border-surface-border">
                    {result.reasoning}
                  </p>
                </div>
              )}

              {result.platform_scores && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Platform Scores (Thompson Samples)</h3>
                  <div className="space-y-3">
                    {Object.entries(result.platform_scores).map(([p, score], i) => (
                      <div key={p} className="animate-fade-in-up" style={{ animationDelay: `${i * 100}ms` }}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-300 capitalize">{p}</span>
                          <span className="text-brand-300">{score.toFixed(3)}</span>
                        </div>
                        <div className="h-1.5 bg-surface-muted rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-brand-500 rounded-full transition-all duration-1000" 
                            style={{ width: `${Math.min(100, Math.max(0, score * 100))}%` }} 
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}