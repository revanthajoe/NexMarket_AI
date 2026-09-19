"use client";

import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, RefreshCw, Send, Zap } from "lucide-react";
import {
  api, AD_COPY_TONES, LANGUAGES, PLATFORM_CHAR_LIMITS,
  AdCopy, Poster, SocialPost,
} from "@/lib/api";

export const AD_COPY_PLATFORMS = ["instagram", "facebook", "telegram", "whatsapp", "email"];

// Kept in sync with backend SUPPORTED_PLATFORMS (posting_service.py).
export const POSTING_PLATFORMS = ["instagram", "facebook", "telegram", "whatsapp"];

const PLATFORM_COLORS: Record<string, string> = {
  instagram: "text-pink-400", facebook: "text-blue-400",
  telegram: "text-sky-400", whatsapp: "text-emerald-400", email: "text-amber-400",
};

export function AdCopyTab({ copies, campaignId, onGenerate, loading }: {
  copies: AdCopy[]; campaignId: string;
  onGenerate: (platforms: string[], tone: string, language: string) => void;
  loading: boolean;
}) {
  const [selected, setSelected]   = useState(0);
  const [tone, setTone]           = useState("professional");
  const [language, setLanguage]   = useState("en");
  const [regenerating, setRegen]  = useState("");

  useEffect(() => {
    api.brandKit.get(campaignId)
      .then(kit => { if (kit.language) setLanguage(kit.language); })
      .catch(() => { /* no kit yet */ });
  }, [campaignId]);

  // Deduplicate copies, keeping only the latest per platform
  const uniqueCopies = useMemo(() => {
    const latest = new Map<string, AdCopy>();
    copies.forEach(c => latest.set(c.platform, c));
    return Array.from(latest.values());
  }, [copies]);

  const copy = uniqueCopies[selected];

  const copyToClipboard = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} copied`);
    } catch {
      toast.error("Clipboard unavailable");
    }
  };

  const regenerateOne = async (platform: string) => {
    setRegen(platform);
    try {
      await onGenerate([platform], tone, language);
    } finally {
      setRegen("");
    }
  };

  const limit = copy ? PLATFORM_CHAR_LIMITS[copy.platform] : undefined;
  const bodyLength = copy?.body?.length ?? 0;
  const overLimit = limit !== undefined && bodyLength > limit;

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="glass-dynamic rounded-xl p-4 flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <label htmlFor="adcopy-tone" className="block text-xs text-slate-400 font-medium">Tone</label>
          <select id="adcopy-tone" name="adcopy-tone" value={tone} onChange={e => setTone(e.target.value)}
            className="bg-surface-muted border border-surface-border rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-brand-400">
            {AD_COPY_TONES.map(t => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="adcopy-language" className="block text-xs text-slate-400 font-medium">Language</label>
          <select id="adcopy-language" name="adcopy-language" value={language} onChange={e => setLanguage(e.target.value)}
            className="bg-surface-muted border border-surface-border rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-brand-400">
            {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </div>
        <button
          onClick={() => onGenerate(AD_COPY_PLATFORMS, tone, language)}
          disabled={loading}
          className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 ml-auto">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
          Generate All Platforms
        </button>
      </div>

      {uniqueCopies.length === 0 ? (
        <div className="glass rounded-xl p-10 border border-surface-border text-center text-slate-500 text-sm">
          No ad copies yet. Click Generate to create platform-specific copy.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          <div className="space-y-1">
            {uniqueCopies.map((c, i) => (
              <button key={c.id} onClick={() => setSelected(i)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  i === selected ? "bg-brand-500/20 text-brand-300" : "text-slate-400 hover:text-slate-200 hover:bg-surface-muted"
                }`}>
                <span className={PLATFORM_COLORS[c.platform] || "text-slate-400"}>
                  {c.platform.charAt(0).toUpperCase() + c.platform.slice(1)}
                </span>
              </button>
            ))}
          </div>
          {copy && (
            <div className="lg:col-span-3 glass-dynamic rounded-xl p-5 space-y-4 animate-scale-up">
              <div className="flex items-center justify-between gap-3">
                <span className={`text-xs font-medium ${PLATFORM_COLORS[copy.platform] || "text-slate-400"}`}>
                  {copy.platform.charAt(0).toUpperCase() + copy.platform.slice(1)}
                  {copy.tone && <span className="text-slate-600"> · {copy.tone}</span>}
                  {copy.fallback && (
                    <span className="badge-mock px-1.5 py-0.5 rounded ml-2" title="Generation failed — this is placeholder English copy, not a real result in the requested language">
                      fallback
                    </span>
                  )}
                </span>
                <button
                  onClick={() => regenerateOne(copy.platform)}
                  disabled={loading || !!regenerating}
                  className="text-xs px-2.5 py-1 rounded-lg border border-surface-border text-slate-400 hover:text-slate-200 hover:bg-surface-muted flex items-center gap-1.5 disabled:opacity-50">
                  {regenerating === copy.platform
                    ? <Loader2 size={12} className="animate-spin" />
                    : <RefreshCw size={12} />}
                  Regenerate
                </button>
              </div>

              {copy.headline && (
                <div className="flex items-start justify-between gap-3">
                  <p className="text-base font-semibold text-white">{copy.headline}</p>
                  <button onClick={() => copyToClipboard("Headline", copy.headline!)}
                    className="text-xs text-slate-500 hover:text-brand-300 flex-shrink-0">Copy</button>
                </div>
              )}

              <div className="space-y-1">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-slate-300 whitespace-pre-wrap">{copy.body}</p>
                  <button onClick={() => copyToClipboard("Body", copy.body)}
                    className="text-xs text-slate-500 hover:text-brand-300 flex-shrink-0">Copy</button>
                </div>
                {limit !== undefined && (
                  <p className={`text-[10px] font-mono ${overLimit ? "text-red-400" : "text-slate-600"}`}>
                    {bodyLength} / {limit} characters{overLimit ? " — over the platform limit" : ""}
                  </p>
                )}
              </div>

              {copy.cta_variants?.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {copy.cta_variants.map((cta, i) => (
                    <button key={i} onClick={() => copyToClipboard("CTA", cta)}
                      className="px-3 py-1 rounded-full text-xs bg-brand-500/20 text-brand-300 border border-brand-500/30 hover:bg-brand-500/30">
                      {cta}
                    </button>
                  ))}
                </div>
              )}

              {copy.hashtags?.length > 0 && (
                <div className="flex items-start justify-between gap-3">
                  <p className="text-xs text-slate-500">{copy.hashtags.map(h => `#${h}`).join(" ")}</p>
                  <button onClick={() => copyToClipboard("Hashtags", copy.hashtags!.map(h => `#${h}`).join(" "))}
                    className="text-xs text-slate-500 hover:text-brand-300 flex-shrink-0">Copy</button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PostingTab({ posts, campaignId, copies, posters, onPost, loading }: {
  posts: SocialPost[]; campaignId: string; copies: AdCopy[]; posters: Poster[];
  onPost: (platforms: string[], ad_copy_id?: string, poster_id?: string) => void;
  loading: boolean;
}) {
  const [selected, setSelected] = useState<string[]>(["instagram"]);
  const icons: Record<string, string> = {
    posted: "✅", posting: "⏳", scheduled: "📅", failed: "❌", pending: "🔄",
  };

  const togglePlatform = (p: string) =>
    setSelected(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);

  return (
    <div className="space-y-6">
      <div className="glass-dynamic rounded-xl p-5 space-y-4 animate-fade-in-up">
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-wide mb-2">Platforms</p>
          <div className="flex flex-wrap gap-2">
            {POSTING_PLATFORMS.map(p => (
              <label key={p}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm cursor-pointer border ${
                  selected.includes(p)
                    ? "border-brand-400 bg-brand-500/10 text-brand-200"
                    : "border-surface-border text-slate-400"
                }`}>
                <input type="checkbox" className="accent-brand-500"
                  checked={selected.includes(p)}
                  onChange={() => togglePlatform(p)} />
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </label>
            ))}
          </div>
        </div>
        <div className="flex justify-end">
          <button onClick={() => onPost(selected, copies[0]?.id, posters[0]?.id)}
            disabled={loading || selected.length === 0}
            className="btn-brand px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 flex-shrink-0 disabled:opacity-50">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Post Now{selected.length > 1 ? ` (${selected.length} platforms)` : ""}
          </button>
        </div>
      </div>
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-400">Post History</h3>
        {posts.length === 0 ? (
          <div className="glass rounded-xl p-8 border border-surface-border text-center text-slate-500 text-sm">
            No posts yet
          </div>
        ) : posts.map((p, i) => (
          <div key={p.id} className="glass-dynamic rounded-xl p-4 flex items-center justify-between animate-fade-in-up" style={{ animationDelay: `${i * 100}ms` }}>
            <div className="flex items-center gap-3">
              <span className="text-lg">{icons[p.status] || "🔄"}</span>
              <div>
                <p className="text-sm font-medium text-white">{p.platform}</p>
                <p className="text-xs text-slate-500">
                  {p.is_mock && <span className="badge-mock px-1.5 py-0.5 rounded mr-1">mock</span>}
                  {p.platform_post_id || "No ID yet"}
                </p>
              </div>
            </div>
            <div className="text-right">
              <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                p.status === "posted" ? "badge-posted" : p.status === "failed" ? "badge-failed" : "badge-pending"
              }`}>{p.status}</span>
              {p.platform_url && (
                <a href={p.platform_url} target="_blank" rel="noreferrer"
                  className="block text-xs text-brand-400 hover:underline mt-1">View Post ↗</a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
