"use client";

import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, RefreshCw, Send, Zap } from "lucide-react";
import {
  api, AD_COPY_TONES, LANGUAGES, PLATFORM_CHAR_LIMITS,
  AdCopy, Poster, SocialPost,
} from "@/lib/api";

export const AD_COPY_PLATFORMS = ["instagram", "facebook", "telegram", "whatsapp", "email"];

export const POSTING_PLATFORMS = ["instagram", "facebook", "telegram", "whatsapp"];

const PLATFORM_COLORS: Record<string, string> = {
  instagram: "text-rose-500", facebook: "text-blue-600",
  telegram: "text-sky-500", whatsapp: "text-emerald-500", email: "text-amber-500",
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
      .then((kit) => { if (kit.language) setLanguage(kit.language); })
      .catch(() => { /* no kit yet */ });
  }, [campaignId]);

  const uniqueCopies = useMemo(() => {
    const latest = new Map<string, AdCopy>();
    copies.forEach((c) => latest.set(c.platform, c));
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
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 flex flex-wrap items-end gap-4 animate-fade-in-up">
        <div className="space-y-1.5 min-w-[140px]">
          <label htmlFor="adcopy-tone" className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Tone</label>
          <select id="adcopy-tone" name="adcopy-tone" value={tone} onChange={(e) => setTone(e.target.value)}
            className="input-dark w-full text-sm bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2 text-slate-700 dark:text-slate-200">
            {AD_COPY_TONES.map((t) => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5 min-w-[140px]">
          <label htmlFor="adcopy-language" className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Language</label>
          <select id="adcopy-language" name="adcopy-language" value={language} onChange={(e) => setLanguage(e.target.value)}
            className="input-dark w-full text-sm bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2 text-slate-700 dark:text-slate-200">
            {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </div>
        <button
          onClick={() => onGenerate(AD_COPY_PLATFORMS, tone, language)}
          disabled={loading}
          className="btn-brand px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 flex-1 md:flex-none md:ml-auto">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
          Generate All Platforms
        </button>
      </div>

      {uniqueCopies.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-xl p-12 text-center text-slate-500 dark:text-slate-400 text-sm flex flex-col items-center justify-center gap-2">
          <Send size={24} className="text-slate-300 dark:text-slate-700" />
          No ad copies yet. Click Generate to create platform-specific copy.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
          <div className="space-y-1.5">
            {uniqueCopies.map((c, i) => (
              <button key={c.id} onClick={() => setSelected(i)}
                className={`w-full text-left px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-150 border ${
                  i === selected
                    ? "bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800/50 shadow-sm"
                    : "bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                }`}>
                <span className={i === selected ? PLATFORM_COLORS[c.platform] || "text-slate-800 dark:text-slate-200" : ""}>
                  {c.platform.charAt(0).toUpperCase() + c.platform.slice(1)}
                </span>
              </button>
            ))}
          </div>
          
          {copy && (
            <div className="lg:col-span-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 space-y-5 animate-scale-up">
              <div className="flex items-center justify-between gap-3 border-b border-slate-100 dark:border-slate-800 pb-4">
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-bold ${PLATFORM_COLORS[copy.platform] || "text-slate-700 dark:text-slate-200"}`}>
                    {copy.platform.charAt(0).toUpperCase() + copy.platform.slice(1)}
                  </span>
                  {copy.tone && <span className="text-xs text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded capitalize">{copy.tone}</span>}
                  {copy.fallback && (
                    <span className="text-[10px] bg-rose-50 dark:bg-rose-900/30 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800/50 px-1.5 py-0.5 rounded font-semibold" title="Generation failed — this is placeholder fallback copy">
                      FALLBACK
                    </span>
                  )}
                </div>
                <button
                  onClick={() => regenerateOne(copy.platform)}
                  disabled={loading || !!regenerating}
                  className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-800 font-medium flex items-center gap-1.5 disabled:opacity-50 transition-colors">
                  {regenerating === copy.platform ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                  Regenerate
                </button>
              </div>

              {copy.headline && (
                <div className="flex items-start justify-between gap-4">
                  <p className="text-lg font-bold text-slate-900 leading-snug">{copy.headline}</p>
                  <button onClick={() => copyToClipboard("Headline", copy.headline!)} className="text-xs text-blue-600 font-medium hover:underline flex-shrink-0 pt-1">Copy</button>
                </div>
              )}

              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-4">
                  <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{copy.body}</p>
                  <button onClick={() => copyToClipboard("Body", copy.body)} className="text-xs text-blue-600 font-medium hover:underline flex-shrink-0 pt-0.5">Copy</button>
                </div>
                {limit !== undefined && (
                  <p className={`text-[10px] font-mono mt-2 ${overLimit ? "text-rose-600 font-semibold bg-rose-50 inline-block px-2 py-0.5 rounded" : "text-slate-400"}`}>
                    {bodyLength} / {limit} characters{overLimit ? " — over the platform limit" : ""}
                  </p>
                )}
              </div>

              {copy.cta_variants?.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-2">
                  {copy.cta_variants.map((cta, i) => (
                    <button key={i} onClick={() => copyToClipboard("CTA", cta)}
                      className="px-3 py-1.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200 hover:bg-slate-200 transition-colors">
                      {cta}
                    </button>
                  ))}
                </div>
              )}

              {copy.hashtags?.length > 0 && (
                <div className="flex items-start justify-between gap-4 pt-2 border-t border-slate-100">
                  <p className="text-sm font-medium text-blue-600 leading-relaxed">{copy.hashtags.map((h) => `#${h}`).join(" ")}</p>
                  <button onClick={() => copyToClipboard("Hashtags", copy.hashtags!.map((h) => `#${h}`).join(" "))} className="text-xs text-blue-600 font-medium hover:underline flex-shrink-0 pt-0.5">Copy</button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PostingTab({ posts, campaignId, copies, posters, onPost, loading, selectedPosterId }: {
  posts: SocialPost[]; campaignId: string; copies: AdCopy[]; posters: Poster[];
  onPost: (platforms: string[], ad_copy_id?: string, poster_id?: string) => void;
  loading: boolean; selectedPosterId: string | null;
}) {
  const [selected, setSelected] = useState<string[]>(["instagram"]);
  const icons: Record<string, string> = {
    posted: "✅", posting: "⏳", scheduled: "📅", failed: "❌", pending: "🔄",
  };

  const togglePlatform = (p: string) => setSelected((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]);

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 space-y-5 animate-fade-in-up">
        <div>
          <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-3">Publish to Platforms</p>
          <div className="flex flex-wrap gap-2.5">
            {POSTING_PLATFORMS.map((p) => (
              <label key={p}
                className={`flex items-center gap-2.5 px-4 py-2 rounded-xl text-sm font-semibold cursor-pointer border transition-colors ${
                  selected.includes(p)
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 shadow-sm"
                    : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"
                }`}>
                <input type="checkbox" className="accent-blue-600 w-4 h-4 rounded border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700"
                  checked={selected.includes(p)}
                  onChange={() => togglePlatform(p)} />
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </label>
            ))}
          </div>
        </div>
        <div className="flex justify-end pt-2 border-t border-slate-100 dark:border-slate-800">
          <button onClick={() => onPost(selected, copies[0]?.id, selectedPosterId ?? undefined)}
            disabled={loading || selected.length === 0}
            className="btn-brand px-6 py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 w-full md:w-auto disabled:opacity-50">
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            Post Now{selected.length > 1 ? ` (${selected.length} platforms)` : ""}
          </button>
        </div>
      </div>

      <div className="space-y-3 pt-2">
        <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">Publish History</h3>
        {posts.length === 0 ? (
          <div className="bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 rounded-xl p-8 text-center text-slate-500 dark:text-slate-400 text-sm">
            No posts published yet
          </div>
        ) : posts.map((p, i) => (
          <div key={p.id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 flex items-center justify-between shadow-sm animate-fade-in-up" style={{ animationDelay: `${i * 80}ms` }}>
            <div className="flex items-center gap-4">
              <span className="text-2xl leading-none">{icons[p.status] || "🔄"}</span>
              <div>
                <p className="text-sm font-bold text-slate-800 dark:text-slate-200 capitalize">{p.platform}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 flex items-center">
                  {p.is_mock ? (
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800/50 font-semibold mr-2">MOCK</span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/50 font-semibold mr-2">LIVE</span>
                  )}
                  {p.platform_post_id || "No ID assigned"}
                </p>
              </div>
            </div>
            <div className="text-right">
              <span className={`text-xs px-2.5 py-1 rounded-full font-semibold border ${
                p.status === "posted" ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/50" : 
                p.status === "failed" ? "bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800/50" : "bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800/50"
              }`}>{p.status}</span>
              {p.platform_url && (
                <a href={p.platform_url} target="_blank" rel="noreferrer"
                  className="block text-xs font-medium text-blue-600 hover:underline mt-1.5">View Post ↗</a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
