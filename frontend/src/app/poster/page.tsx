"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Image as ImageIcon, Zap, Star } from "lucide-react";
import { api, Campaign, Poster, PosterEvaluation } from "@/lib/api";
import { getPosterImageUrl, isMockPoster } from "@/lib/poster";
import { LANGUAGES } from "@/lib/api";

// Mock/error image fallback (same pattern as campaign detail)
function PosterImage({
  src, provider, alt, onClick,
}: {
  src: string; provider: string; alt: string; onClick: () => void;
}) {
  const [errored, setErrored] = useState(false);
  const resolvedSrc = getPosterImageUrl(src);
  const isMock = isMockPoster(provider);

  if (isMock) {
    return (
      <div
        className="aspect-[3/4] bg-slate-50 border-2 border-dashed border-slate-200 rounded-t-lg
                   flex flex-col items-center justify-center gap-2"
      >
        <ImageIcon size={24} className="text-slate-300" />
        <p className="text-xs text-slate-400 font-medium">Mock Provider</p>
        <p className="text-[10px] text-slate-300 font-mono px-4 text-center">No real image generated.</p>
      </div>
    );
  }

  if (errored) {
    return (
      <div
        className="aspect-[3/4] bg-slate-50 border-2 border-dashed border-slate-200 rounded-t-lg
                   flex flex-col items-center justify-center gap-2"
        title="Image unavailable"
      >
        <ImageIcon size={24} className="text-slate-300" />
        <p className="text-xs text-slate-400 font-medium">Unavailable</p>
        <p className="text-[10px] text-slate-300 font-mono">provider: {provider}</p>
      </div>
    );
  }

  return (
    <div
      className="aspect-[3/4] bg-white overflow-hidden relative group cursor-pointer"
      onClick={onClick}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={resolvedSrc}
        alt={alt}
        className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
        onError={() => setErrored(true)}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent opacity-0
                      group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-4">
        <p className="text-xs text-white line-clamp-2">{alt}</p>
      </div>
    </div>
  );
}

export default function PosterGalleryPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<string>("");
  const [posters, setPosters] = useState<Poster[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [evaluations, setEvaluations] = useState<Record<string, PosterEvaluation>>({});
  const [lightbox, setLightbox] = useState<string | null>(null);
  const [language, setLanguage] = useState("en");

  useEffect(() => {
    api.campaigns.list().then((res) => {
      setCampaigns(res);
      if (res.length > 0) setSelectedCampaign(res[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedCampaign) return;
    api.brandKit.get(selectedCampaign)
      .then((kit) => { if (kit.language) setLanguage(kit.language); })
      .catch(() => {});
  }, [selectedCampaign]);

  useEffect(() => {
    if (!selectedCampaign) return;
    setLoading(true);
    api.posters.getByCampaign(selectedCampaign)
      .then((items) => setPosters(items.filter((poster) => !isMockPoster(poster.provider))))
      .catch(() => toast.error("Failed to load posters"))
      .finally(() => setLoading(false));
  }, [selectedCampaign]);

  const handleGenerate = async () => {
    if (!selectedCampaign) return;
    setGenerating(true);
    try {
      const newPosters = await api.posters.generate(selectedCampaign, 1, language);
      setPosters((prev) => [...newPosters, ...prev]);
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
      setEvaluations((prev) => ({ ...prev, [posterId]: evaluation }));
      toast.success("Vision evaluation complete");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to evaluate poster");
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
              <ImageIcon size={18} className="text-blue-600" />
            </div>
            Creative Poster Studio
          </h1>
          <p className="text-slate-500 mt-1.5 text-sm">
            Generate, evaluate, and manage AI marketing visuals via SDXL
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 animate-fade-in-up">
        <div className="grid grid-cols-1 md:grid-cols-[minmax(220px,1fr)_auto_minmax(180px,1fr)] gap-4 items-end">
          <div className="min-w-0 space-y-1.5">
            <label htmlFor="poster-campaign" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Campaign
            </label>
            <select
              id="poster-campaign"
              name="poster-campaign"
              className="input-dark w-full min-w-0"
              value={selectedCampaign}
              onChange={(e) => setSelectedCampaign(e.target.value)}
            >
              {campaigns.length === 0 && <option value="">No campaigns available</option>}
              {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <button
            onClick={handleGenerate}
            disabled={generating || !selectedCampaign}
            className="btn-brand px-6 py-2.5 rounded-xl font-semibold flex items-center justify-center gap-2 w-full md:w-auto whitespace-nowrap"
          >
            {generating ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />}
            Generate New Visual
          </button>
          <select
            id="poster-gallery-language"
            name="poster-gallery-language"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="input-dark w-full min-w-0 px-3 py-2.5 rounded-xl text-sm"
            aria-label="Poster language"
          >
            {LANGUAGES.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
          </select>
        </div>
      </div>

      {/* Gallery */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <div className="aspect-[3/4] shimmer" />
              <div className="p-4 space-y-2">
                <div className="h-3 w-24 rounded shimmer" />
                <div className="h-8 rounded shimmer" />
              </div>
            </div>
          ))}
        </div>
      ) : posters.length === 0 ? (
        <div className="bg-white border-2 border-dashed border-slate-200 rounded-xl p-16 text-center animate-fade-in-up">
          <ImageIcon size={36} className="text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500 font-medium">No posters generated for this campaign yet.</p>
          <p className="text-slate-400 text-xs mt-1">Use &quot;Generate New Visual&quot; to create AI marketing posters.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
          {posters.map((p, i) => {
            const ev = evaluations[p.id] || p.metadata_?.evaluation;
            return (
              <div
                key={p.id}
                className="bg-white border border-slate-200 rounded-xl overflow-hidden
                           hover:shadow-card-hover hover:-translate-y-0.5 transition-all duration-150 animate-fade-in-up"
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <PosterImage
                  src={p.image_url}
                  provider={p.provider}
                  alt={p.prompt_used || "AI Poster"}
                  onClick={() => setLightbox(p.image_url)}
                />
                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400 font-mono">provider: {p.provider}</span>
                    <span className="text-xs text-slate-400">{new Date(p.created_at).toLocaleDateString()}</span>
                  </div>

                  {!ev ? (
                    <button
                      onClick={() => handleEvaluate(p.id)}
                      className="w-full py-2 rounded-lg text-xs font-medium bg-blue-50 text-blue-700
                                 hover:bg-blue-100 border border-blue-200 transition-colors flex items-center justify-center gap-1.5"
                    >
                      <Star size={11} />
                      Run Vision AI Evaluation
                    </button>
                  ) : (
                    <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                      <div className="flex justify-between items-center mb-1.5">
                        <span className="text-xs text-slate-500 font-medium">Vision Score</span>
                        <span className={`text-sm font-bold ${
                          ev.overall_score >= 80 ? "text-emerald-600" :
                          ev.overall_score >= 60 ? "text-amber-600" : "text-rose-600"
                        }`}>
                          {ev.overall_score}/100
                        </span>
                      </div>
                      <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-2">
                        {ev.source_type || "UNKNOWN"}{ev.is_fallback ? " · FALLBACK" : ""}
                      </div>
                      <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            ev.overall_score >= 80 ? "bg-emerald-500" :
                            ev.overall_score >= 60 ? "bg-amber-500" : "bg-rose-500"
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
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-sm"
          onClick={() => setLightbox(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] w-full mx-4 animate-scale-up"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setLightbox(null)}
              className="absolute -top-10 right-0 text-white/80 hover:text-white text-sm flex items-center gap-1.5"
            >
              <span className="text-xl leading-none">✕</span> Close
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
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