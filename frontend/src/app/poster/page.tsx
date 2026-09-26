"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Image as ImageIcon, Zap } from "lucide-react";
import { api, Campaign, Poster, PosterEvaluation } from "@/lib/api";

export default function PosterGalleryPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<string>("");
  const [posters, setPosters] = useState<Poster[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [evaluations, setEvaluations] = useState<Record<string, PosterEvaluation>>({});
  const [lightbox, setLightbox] = useState<string | null>(null);

  useEffect(() => {
    api.campaigns.list().then(res => {
      setCampaigns(res);
      if (res.length > 0) setSelectedCampaign(res[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedCampaign) return;
    setLoading(true);
    api.posters.getByCampaign(selectedCampaign)
      .then(setPosters)
      .catch(() => toast.error("Failed to load posters"))
      .finally(() => setLoading(false));
  }, [selectedCampaign]);

  const handleGenerate = async () => {
    if (!selectedCampaign) return;
    setGenerating(true);
    try {
      const newPosters = await api.posters.generate(selectedCampaign, 1);
      setPosters(prev => [...newPosters, ...prev]);
      toast.success("Poster generated successfully");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to generate poster");
    } finally {
      setGenerating(false);
    }
  };

  const handleEvaluate = async (posterId: string) => {
    try {
      const evaluation = await api.posters.evaluate(posterId);
      setEvaluations(prev => ({ ...prev, [posterId]: evaluation }));
      toast.success("Vision evaluation complete");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to evaluate poster");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center">
            <ImageIcon size={20} className="text-brand-400" />
          </div>
          Creative Poster Studio
        </h1>
        <p className="text-slate-400 mt-2 text-sm">
          Generate, evaluate, and manage AI marketing visuals via SDXL
        </p>
      </div>

      <div className="glass-dynamic rounded-2xl p-6 animate-fade-in-up">
        <div className="flex flex-col md:flex-row gap-4 items-end">
          <div className="flex-1 space-y-1.5 w-full">
            <label htmlFor="poster-campaign" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Select Campaign</label>
            <select 
              id="poster-campaign"
              name="poster-campaign"
              className="input-dark" 
              value={selectedCampaign} 
              onChange={e => setSelectedCampaign(e.target.value)}
            >
              {campaigns.length === 0 && <option value="">No campaigns available</option>}
              {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <button 
            onClick={handleGenerate} 
            disabled={generating || !selectedCampaign}
            className="btn-brand px-6 py-2.5 rounded-xl font-medium flex items-center justify-center gap-2 w-full md:w-auto"
          >
            {generating ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
            Generate New Visual
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center p-10"><Loader2 className="animate-spin text-brand-400" /></div>
      ) : posters.length === 0 ? (
        <div className="p-16 border border-dashed border-surface-border rounded-xl text-center text-slate-500 text-sm animate-fade-in-up">
          No posters generated for this campaign yet.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {posters.map((p, i) => {
            const ev = evaluations[p.id] || p.metadata_?.evaluation;
            return (
              <div key={p.id} className="glass-dynamic rounded-xl overflow-hidden animate-fade-in-up group" style={{ animationDelay: `${i * 100}ms` }}>
                <div 
                  className="aspect-square relative cursor-pointer overflow-hidden"
                  onClick={() => setLightbox(p.image_url)}
                >
                  <img 
                    src={p.image_url} 
                    alt="AI Poster" 
                    className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-4">
                    <p className="text-xs text-white line-clamp-2">{p.prompt_used || "No prompt details"}</p>
                  </div>
                </div>
                <div className="p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400">Provider: {p.provider}</span>
                    <span className="text-xs text-slate-400">{new Date(p.created_at).toLocaleDateString()}</span>
                  </div>
                  
                  {!ev ? (
                    <button 
                      onClick={() => handleEvaluate(p.id)}
                      className="w-full py-2 rounded-lg text-xs font-medium bg-brand-500/10 text-brand-300 hover:bg-brand-500/20 border border-brand-500/20 transition-colors"
                    >
                      Run Vision AI Evaluation
                    </button>
                  ) : (
                    <div className="bg-surface-muted/30 rounded-lg p-3 border border-surface-border">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-xs text-slate-400 uppercase tracking-wide">Vision Score</span>
                        <span className={`text-sm font-bold ${
                          ev.overall_score >= 80 ? 'text-emerald-400' :
                          ev.overall_score >= 60 ? 'text-amber-400' : 'text-rose-400'
                        }`}>
                          {ev.overall_score}/100
                        </span>
                      </div>
                      <div className="text-[10px] uppercase tracking-wide text-amber-300 mb-2">
                        {ev.source_type || "UNKNOWN"}{ev.is_fallback ? " · FALLBACK" : ""}
                      </div>
                      <div className="h-1.5 bg-surface-muted rounded-full overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${
                            ev.overall_score >= 80 ? 'bg-emerald-500' :
                            ev.overall_score >= 60 ? 'bg-amber-500' : 'bg-rose-500'
                          }`} 
                          style={{ width: `${ev.overall_score}%` }} 
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md transition-all duration-300"
          onClick={() => setLightbox(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] w-full mx-4 animate-scale-up"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setLightbox(null)}
              className="absolute -top-12 right-0 text-white hover:text-brand-400 transition-colors bg-black/50 p-2 rounded-full backdrop-blur-md"
            >
              ✕
            </button>
            <img
              src={lightbox}
              alt="Full resolution"
              className="w-full h-auto max-h-[85vh] object-contain rounded-xl shadow-2xl"
            />
          </div>
        </div>
      )}
    </div>
  );
}