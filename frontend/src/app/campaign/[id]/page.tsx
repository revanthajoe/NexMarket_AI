"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import toast from "react-hot-toast";
import dynamic from "next/dynamic";
import {
  Loader2, Image as ImageIcon, Send, TrendingUp,
  Target, Zap, RefreshCw, CheckCircle2,
} from "lucide-react";
import {
  api, invalidateCache, PIPELINE_STEPS, LANGUAGES,
  Campaign, Poster, PosterEvaluation, AdCopy,
  SocialPost, Forecast, Optimization, BrandKitInfo,
} from "@/lib/api";
import { AdCopyTab, PostingTab } from "@/components/campaign/CampaignTabs";

// Dynamic imports for heavy chart components — split from main bundle
const PosterRadarChart = dynamic(
  () => import("@/components/charts/PosterRadarChart").then((m) => m.PosterRadarChart),
  { ssr: false, loading: () => <div className="h-[220px] shimmer rounded-xl" /> }
);
const ForecastLineChart = dynamic(
  () => import("@/components/charts/ForecastLineChart").then((m) => m.ForecastLineChart),
  { ssr: false, loading: () => <div className="h-[280px] shimmer rounded-xl" /> }
);

type TabId = "overview" | "poster" | "adcopy" | "posting" | "forecast" | "optimize";

const POLL_INTERVAL_MS = 3000;
// Backstop only — the backend self-heals a stuck "generating" campaign after
// 20 minutes (n8n_webhooks.STALE_GENERATING_TIMEOUT_SECONDS). This just makes
// sure a client that's open the whole time doesn't poll forever if that ever
// doesn't happen (e.g. the status call itself keeps erroring).
const MAX_POLL_MS = 25 * 60 * 1000;

const STATUS_BADGE_CLASSES: Record<string, string> = {
  draft: "badge-pending", generating: "badge-pending", ready: "badge-mock",
  posted: "badge-posted", failed: "badge-failed",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${STATUS_BADGE_CLASSES[status] || "badge-pending"}`}>
      {status}
    </span>
  );
}

const TABS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "overview",  label: "Overview",  icon: Zap },
  { id: "poster",    label: "Poster",    icon: ImageIcon },
  { id: "adcopy",    label: "Ad Copy",   icon: Send },
  { id: "posting",   label: "Posting",   icon: Send },
  { id: "forecast",  label: "Forecast",  icon: TrendingUp },
  { id: "optimize",  label: "Optimize",  icon: Target },
];

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [campaign, setCampaign]       = useState<Campaign | null>(null);
  const [posters, setPosters]         = useState<Poster[]>([]);
  const [eval_, setEval]              = useState<PosterEvaluation | null>(null);
  const [copies, setCopies]           = useState<AdCopy[]>([]);
  const [posts, setPosts]             = useState<SocialPost[]>([]);
  const [forecast, setForecast]       = useState<Forecast | null>(null);
  const [optimization, setOptimization] = useState<Optimization | null>(null);
  const [tab, setTab]                 = useState<TabId>("overview");
  const [loading, setLoading]         = useState(true);
  const [actionLoading, setActionLoading] = useState("");
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [c, ps, ads, sps] = await Promise.all([
        api.campaigns.get(id),
        api.posters.getByCampaign(id).catch(() => [] as Poster[]),
        api.adcopy.getByCampaign(id).catch(() => [] as AdCopy[]),
        api.posting.getBycampaign(id).catch(() => [] as SocialPost[]),
      ]);
      setCampaign(c); setPosters(ps); setCopies(ads); setPosts(sps);
    } catch {
      toast.error("Failed to load campaign");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Generic action runner — reloads page data after action EXCEPT for poster
  // generation which sets state directly to avoid re-triggering generation.
  const runAction = useCallback(async (action: string, fn: () => Promise<unknown>) => {
    setActionLoading(action);
    try {
      await fn();
      // Poster Generation manages its own state; other actions need a reload.
      if (action !== "Poster Generation") {
        await load();
      }
      toast.success(`${action} complete!`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`[runAction] ${action} failed:`, msg);
      toast.error(`${action} failed: ${msg}`);
    } finally {
      setActionLoading("");
    }
  }, [load]);

  // The pipeline trigger only *queues* work server-side, so success can't be
  // reported from the trigger response — poll campaign status until it settles.
  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const runPipeline = useCallback(async () => {
    setActionLoading("Full Pipeline");
    setPipelineStatus("generating");
    try {
      await api.n8n.trigger(id, PIPELINE_STEPS);
    } catch (err: unknown) {
      setActionLoading("");
      setPipelineStatus(null);
      toast.error(`Failed to start pipeline: ${err instanceof Error ? err.message : String(err)}`);
      return;
    }

    stopPolling();
    const startedAt = Date.now();
    pollRef.current = setInterval(async () => {
      let snapshot;
      try {
        snapshot = await api.n8n.status(id);
      } catch {
        return; // transient — keep polling
      }
      setPipelineStatus(snapshot.status);
      if (snapshot.status === "generating") {
        if (Date.now() - startedAt > MAX_POLL_MS) {
          stopPolling();
          setActionLoading("");
          setPipelineStatus(null);
          toast.error("Still generating after 25 minutes — check the backend, then refresh.");
        }
        return;
      }

      stopPolling();
      setActionLoading("");
      setPipelineStatus(null);
      // The pipeline wrote to the DB without any request from this client, so
      // cached GETs from before it ran are stale.
      invalidateCache();
      await load();
      if (snapshot.status === "failed") {
        toast.error("Pipeline failed — check the backend logs.");
      } else {
        toast.success("Pipeline complete!");
      }
    }, POLL_INTERVAL_MS);
  }, [id, load, stopPolling]);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 size={32} className="animate-spin text-brand-400" />
    </div>
  );
  if (!campaign) return <p className="text-slate-500">Campaign not found.</p>;

  return (
    <div className="space-y-6">
      {/* Campaign Header */}
      <div className="glass-dynamic animate-fade-in-up rounded-2xl p-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-xl font-bold text-white">{campaign.name}</h1>
              <StatusBadge status={campaign.status} />
            </div>
            <p className="text-sm text-slate-400">{campaign.product_name} · {campaign.campaign_goal} · {campaign.preferred_platform}</p>
          </div>
          <button
            onClick={runPipeline}
            disabled={!!actionLoading}
            className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2"
          >
            {actionLoading === "Full Pipeline" ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            {actionLoading === "Full Pipeline" ? "Running…" : "Run Pipeline"}
          </button>
        </div>

        {pipelineStatus && (
          <div className="mt-4 pt-4 border-t border-surface-border">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Loader2 size={12} className="animate-spin text-brand-400" />
              <span>
                Pipeline running — poster, ad copy, evaluation, forecast, optimization and posting.
                This takes several minutes.
              </span>
            </div>
            <div className="mt-2 h-1 bg-surface-muted rounded-full overflow-hidden">
              <div className="h-full w-1/3 bg-gradient-to-r from-brand-500 to-brand-400 animate-pulse rounded-full" />
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-surface-border pb-1">
        {TABS.map(({ id: tid, label, icon: Icon }) => (
          <button
            key={tid}
            onClick={() => setTab(tid)}
            className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
              tab === tid
                ? "text-brand-300 border-b-2 border-brand-400 bg-brand-500/10"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <Icon size={14} />{label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="animate-fade-in-up delay-100">
        {tab === "overview" && <OverviewTab campaign={campaign} copies={copies} posts={posts} />}
      {tab === "poster" && (
        <PosterTab
          posters={posters} eval_={eval_} campaignId={id}
          onGenerate={(language: string) => runAction("Poster Generation", async () => {
            const p = await api.posters.generate(id, 2, language);
            setPosters(p);
            if (p[0]) {
              try {
                const ev = await api.posters.evaluate(p[0].id);
                setEval(ev);
              } catch (evErr) {
                console.warn("[PosterTab] Evaluation failed, continuing:", evErr);
              }
            }
          })}
          loading={actionLoading === "Poster Generation"}
        />
      )}
      {tab === "adcopy" && (
        <AdCopyTab copies={copies} campaignId={id}
          onGenerate={(platforms: string[], tone: string, language: string) =>
            runAction("Ad Copy", async () => {
              const fresh = await api.adcopy.generate(id, platforms, tone, language);
              // Regenerating a single platform must not wipe the other platforms'
              // copy out of view — merge instead of replacing the whole list.
              setCopies(prev => [...prev, ...fresh]);
            })}
          loading={actionLoading === "Ad Copy"}
        />
      )}
      {tab === "posting" && (
        <PostingTab posts={posts} campaignId={id} copies={copies} posters={posters}
          onPost={(platforms, ad_copy_id, poster_id) =>
            runAction("Post", () => api.posting.publishCampaign(id, { platforms, ad_copy_id, poster_id }))
          }
          loading={actionLoading === "Post"}
        />
      )}
      {tab === "forecast" && (
        <ForecastTab forecast={forecast} campaignId={id}
          onForecast={async () => {
            const f = await api.forecast.create(id, 7);
            setForecast(f);
          }}
          loading={actionLoading === "Forecast"}
          runAction={runAction}
        />
      )}
      {tab === "optimize" && (
        <OptimizeTab optimization={optimization} campaignId={id}
          onOptimize={async () => {
            const o = await api.optimize.run(id, campaign.budget || 500);
            setOptimization(o);
          }}
          loading={actionLoading === "Optimize"}
          runAction={runAction}
        />
      )}
      </div>
    </div>
  );
}

// ── Sub-tabs ──────────────────────────────────────────────────────────────────

function OverviewTab({ campaign, copies, posts }: {
  campaign: Campaign; copies: AdCopy[]; posts: SocialPost[];
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="glass-dynamic rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-brand-400 uppercase tracking-wide">Campaign Details</h3>
        {[
          ["Product",     campaign.product_name],
          ["Description", campaign.description],
          ["Offer",       campaign.offer],
          ["Target",      campaign.target_audience],
          ["Goal",        campaign.campaign_goal],
          ["Platform",    campaign.preferred_platform],
          ["Budget",      campaign.budget ? `$${campaign.budget}` : "Not set"],
        ].map(([k, v]) => (
          <div key={k} className="flex gap-3">
            <span className="text-xs text-slate-500 w-24 flex-shrink-0">{k}</span>
            <span className="text-xs text-slate-300">{v}</span>
          </div>
        ))}
      </div>
      <div className="space-y-4">
        <div className="glass-dynamic rounded-xl p-5 delay-75 animate-fade-in-up">
          <h3 className="text-sm font-semibold text-brand-400 uppercase tracking-wide mb-3">Posts</h3>
          {posts.length === 0 ? (
            <p className="text-xs text-slate-500">No posts yet</p>
          ) : posts.map(p => (
            <div key={p.id} className="flex items-center justify-between py-1.5 border-b border-surface-border last:border-0">
              <span className="text-xs text-slate-300">{p.platform}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                p.status === "posted" ? "badge-posted" : p.status === "failed" ? "badge-failed" : "badge-pending"
              }`}>{p.status}</span>
            </div>
          ))}
        </div>
        <div className="glass-dynamic rounded-xl p-5 delay-150 animate-fade-in-up">
          <h3 className="text-sm font-semibold text-brand-400 uppercase tracking-wide mb-3">Ad Copies</h3>
          <p className="text-xs text-slate-400">{copies.length} platform variant{copies.length !== 1 ? "s" : ""} generated</p>
        </div>
      </div>
    </div>
  );
}

function PosterTab({ posters, eval_, campaignId, onGenerate, loading }: {
  posters: Poster[]; eval_: PosterEvaluation | null; campaignId: string;
  onGenerate: (language: string) => void; loading: boolean;
}) {
  const [lightbox, setLightbox]   = useState<string | null>(null);
  const [brandKit, setBrandKit]   = useState<BrandKitInfo | null>(null);
  const [kitLoading, setKitLoad]  = useState(false);
  const [language, setLanguage]   = useState("en");
  const [brandColor, setBrandColor] = useState("");
  const [showKit, setShowKit]     = useState(false);
  // Contact details. Supplying any of these plus a product cutout promotes the
  // poster from the "designed" layout to the full "brochure" layout.
  const [contact, setContact] = useState({
    phone: "", website: "", address_en: "", address_ta: "",
  });

  const loadKit = useCallback(async () => {
    try {
      const kit = await api.brandKit.get(campaignId);
      setBrandKit(kit);
      if (kit.language) setLanguage(kit.language);
      if (kit.brand_color_hex) setBrandColor(kit.brand_color_hex);
      setContact({
        phone:      kit.phone      ?? "",
        website:    kit.website    ?? "",
        address_en: kit.address_en ?? "",
        address_ta: kit.address_ta ?? "",
      });
    } catch { /* no kit yet */ }
  }, [campaignId]);

  // Load on mount, not only when the panel is expanded — otherwise the language
  // dropdown shows the "en" default while a different language is actually saved.
  useEffect(() => { loadKit(); }, [loadKit]);

  const uploadFile = async (type: string, file: File) => {
    setKitLoad(true);
    try {
      await api.brandKit.uploadAsset(campaignId, type, file);
      await loadKit();
      toast.success(`${type} uploaded!`);
    } catch { toast.error(`Failed to upload ${type}`); }
    finally { setKitLoad(false); }
  };

  const saveMeta = async () => {
    setKitLoad(true);
    try {
      await api.brandKit.setMeta(campaignId, {
        language,
        brand_color_hex: brandColor || undefined,
        ...contact,
      });
      await loadKit();
      toast.success("Brand settings saved!");
    } catch { toast.error("Failed to save brand settings"); }
    finally { setKitLoad(false); }
  };

  return (
    <div className="space-y-6">
      {/* Lightbox overlay */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-md transition-all duration-300"
          onClick={() => setLightbox(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] w-full mx-4 animate-scale-up"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              onClick={() => setLightbox(null)}
              className="absolute -top-10 right-0 text-white/70 hover:text-white text-sm flex items-center gap-1"
            >
              <span className="text-lg leading-none">✕</span> Close
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={lightbox}
              alt="Poster preview"
              className="w-full h-auto max-h-[85vh] object-contain rounded-2xl shadow-2xl border border-white/10"
            />
            <div className="mt-3 flex justify-center gap-4">
              <a
                href={lightbox}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-brand-400 hover:text-brand-300 underline"
                onClick={(e) => e.stopPropagation()}
              >
                Open in new tab ↗
              </a>
              <a
                href={lightbox}
                download
                className="text-xs text-emerald-400 hover:text-emerald-300 underline"
                onClick={(e) => e.stopPropagation()}
              >
                Download ↓
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Brand Kit Panel */}
      <div className="glass-dynamic rounded-xl overflow-hidden mb-6">
        <button
          onClick={() => { setShowKit(v => !v); if (!showKit) loadKit(); }}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-slate-300 hover:text-white hover:bg-white/5 transition-colors"
        >
          <span className="flex items-center gap-2">🎨 Brand Kit (Assets · Contact · Language · Brand Colour)</span>
          <span className="text-slate-500">{showKit ? "▲" : "▼"}</span>
        </button>
        {showKit && (
          <div className="px-4 pb-4 pt-2 grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Which layout this kit currently earns, and how to upgrade it.
                Without this the poster silently changes shape with no
                explanation of why. */}
            {brandKit && (
              <div className="md:col-span-2 rounded-lg border border-surface-border bg-surface-muted/50 px-3 py-2">
                <p className="text-xs text-slate-300">
                  Layout:{" "}
                  <span className={brandKit.layout === "brochure" ? "text-emerald-400 font-medium" : "text-brand-300 font-medium"}>
                    {brandKit.layout === "brochure" ? "Full brochure" : "Designed poster"}
                  </span>
                </p>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  {brandKit.layout === "brochure"
                    ? "All zones render, including the contact footer."
                    : "Add a product cutout and a phone or address below to unlock the contact footer."}
                </p>
              </div>
            )}

            {/* Asset uploads */}
            {([
              {type:"logo",           label:"Brand Logo",      hint:"header band"},
              {type:"partner_logo",   label:"Partner Logo",    hint:"optional, header right"},
              {type:"product_cutout", label:"Product Cutout",  hint:"transparent PNG — best hero"},
              {type:"product",        label:"Product Image",   hint:"used if no cutout"},
              {type:"map_image",      label:"Map / Location",  hint:"contact footer thumbnail"},
              {type:"font_bold",      label:"Font (Bold)",     hint:"optional"},
              {type:"font_regular",   label:"Font (Regular)",  hint:"optional"},
            ] as const).map(({type,label,hint}) => (
              <div key={type} className="space-y-1">
                <label htmlFor={`file-upload-${type}`} className="block text-xs text-slate-400 font-medium cursor-pointer">
                  {label} <span className="text-slate-600">({hint})</span>
                </label>
                <input
                  type="file" disabled={kitLoading}
                  id={`file-upload-${type}`} name={`file-upload-${type}`}
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(type, f); }}
                  className="block w-full text-xs text-slate-400 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-brand-500/20 file:text-brand-300 file:text-xs file:font-medium cursor-pointer"
                />
                {brandKit?.[type as keyof BrandKitInfo] && (
                  <p className="text-[10px] text-emerald-400">✓ uploaded</p>
                )}
              </div>
            ))}

            {/* Contact details — these populate the brochure's footer zone. */}
            {([
              {key:"phone",      label:"Phone",             placeholder:"+91 98765 43210"},
              {key:"website",    label:"Website",           placeholder:"example.com"},
              {key:"address_en", label:"Address (English)", placeholder:"12 Main Road, Coimbatore"},
              {key:"address_ta", label:"Address (Local)",   placeholder:"local-language address"},
            ] as const).map(({key,label,placeholder}) => (
              <div key={key} className="space-y-1">
                <label htmlFor={`contact-${key}`} className="block text-xs text-slate-400 font-medium">{label}</label>
                <input
                  type="text" id={`contact-${key}`} name={`contact-${key}`}
                  value={contact[key]} placeholder={placeholder}
                  onChange={e => setContact(c => ({ ...c, [key]: e.target.value }))}
                  className="w-full bg-surface-muted border border-surface-border rounded-lg px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-brand-400"
                />
              </div>
            ))}

            {/* Language */}
            <div className="space-y-1">
              <label htmlFor="poster-language" className="block text-xs text-slate-400 font-medium">Poster Language</label>
              <select
                id="poster-language" name="poster-language"
                value={language} onChange={e => setLanguage(e.target.value)}
                className="w-full bg-surface-muted border border-surface-border rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-brand-400"
              >
                {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>

            {/* Brand Colour */}
            <div className="space-y-1">
              <label htmlFor="brand-color" className="block text-xs text-slate-400 font-medium">Brand Colour (CTA Button)</label>
              <div className="flex gap-2 items-center">
                <input type="color" value={brandColor || "#dc2626"}
                  id="brand-color" name="brand-color"
                  onChange={e => setBrandColor(e.target.value)}
                  className="h-8 w-10 rounded cursor-pointer border-0 bg-transparent"
                />
                <span className="text-xs text-slate-500 font-mono">{brandColor || "#dc2626"}</span>
              </div>
            </div>

            <div className="md:col-span-2 flex justify-end">
              <button onClick={saveMeta} disabled={kitLoading}
                className="btn-brand px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5">
                {kitLoading ? <Loader2 size={12} className="animate-spin" /> : null}
                Save Brand Settings
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Generate button */}
      <div className="flex justify-end items-center gap-3">
        <span className="text-xs text-slate-500">
          Language: <span className="text-slate-300">{LANGUAGES.find(l => l.code === language)?.label ?? language}</span>
        </span>
        <button onClick={() => onGenerate(language)} disabled={loading}
          className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Generate Posters + Evaluate
        </button>
      </div>

      {loading && (
        <div className="glass rounded-xl p-10 border border-surface-border text-center space-y-3">
          <Loader2 size={32} className="animate-spin text-brand-400 mx-auto" />
          <p className="text-sm text-slate-300 font-medium">Multi-Stage AI Pipeline Running…</p>
          <div className="flex flex-wrap justify-center gap-2 mt-2">
            {["🧠 Qwen LLM","🎨 SDXL Generate","🖼️ Composer","🔍 Qwen VL"].map((s,i) => (
              <span key={i} className="text-[11px] px-2.5 py-1 rounded-full bg-brand-500/15 text-brand-300 border border-brand-500/20">{s}</span>
            ))}
          </div>
          <p className="text-xs text-slate-500">Keep this tab visible — browser may suspend background tabs.</p>
        </div>
      )}

      {!loading && posters.length === 0 ? (
        <div className="glass rounded-xl p-10 border border-surface-border text-center text-slate-500 text-sm">
          No posters yet. Click &quot;Generate Posters + Evaluate&quot; to create AI-generated marketing posters.
        </div>
      ) : (
        <div className="space-y-6">
          {posters.map((p, i) => (
            <div key={p.id} className="glass-dynamic rounded-xl overflow-hidden p-4 animate-fade-in-up" style={{ animationDelay: `${i * 100}ms` }}>
              <div className="flex flex-col md:flex-row gap-4 items-center">
                {p.metadata_?.visual_url && (
                  <div className="flex-1 space-y-2 w-full">
                    <p className="text-xs text-slate-400 font-medium text-center">Generated Visual (SDXL)</p>
                    <div 
                      className="aspect-square bg-surface-muted rounded-lg overflow-hidden relative group cursor-pointer"
                      onClick={() => setLightbox(p.metadata_!.visual_url!)}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={p.metadata_.visual_url}
                        alt="Generated Visual"
                        loading="lazy"
                        decoding="async"
                        className="w-full h-full object-contain transition-transform duration-300 group-hover:scale-105"
                      />
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors duration-200 flex items-center justify-center">
                        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-white text-sm font-medium bg-black/50 px-3 py-1.5 rounded-lg">
                          Click to preview
                        </span>
                      </div>
                    </div>
                  </div>
                )}
                
                {p.metadata_?.visual_url && (
                  <div className="hidden md:flex flex-col items-center justify-center px-2 text-slate-500">
                    <span className="text-2xl">→</span>
                    <span className="text-[10px] uppercase tracking-wide">Composer</span>
                  </div>
                )}
                
                <div className="flex-1 space-y-2 w-full">
                  <p className="text-xs text-brand-400 font-medium text-center">Final Marketing Poster</p>
                  <div 
                    className="aspect-square bg-surface-muted rounded-lg overflow-hidden relative group cursor-pointer border border-brand-500/20"
                    onClick={() => setLightbox(p.image_url)}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={p.image_url}
                      alt={`Final Poster ${p.variation_index + 1}`}
                      loading="lazy"
                      decoding="async"
                      className="w-full h-full object-contain transition-transform duration-300 group-hover:scale-105"
                    />
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors duration-200 flex items-center justify-center">
                      <span className="opacity-0 group-hover:opacity-100 transition-opacity text-white text-sm font-medium bg-black/50 px-3 py-1.5 rounded-lg">
                        Click to preview
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="mt-4 pt-3 border-t border-surface-border flex justify-between items-center">
                <p className="text-xs text-slate-400 font-medium">Variation {p.variation_index + 1}</p>
                <p className="text-[10px] text-slate-500 font-mono">Provider: {p.provider} {p.metadata_?.attempts ? `| Attempts: ${p.metadata_.attempts}` : ''}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {eval_ && (
        <div className="glass-dynamic rounded-xl p-6 mt-6 animate-fade-in-up delay-150">
          <h3 className="text-sm font-semibold text-brand-400 mb-4">
            Vision AI Score: <span className="text-white text-xl">{eval_.overall_score}/100</span>
          </h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <PosterRadarChart eval_={eval_} />
            <div className="space-y-3">
              {eval_.strengths?.map((s, i) => (
                <div key={i} className="flex gap-2 text-xs">
                  <CheckCircle2 size={14} className="text-emerald-400 flex-shrink-0 mt-0.5" />
                  <span className="text-slate-300">{s}</span>
                </div>
              ))}
              {eval_.suggestions?.map((s, i) => (
                <div key={i} className="flex gap-2 text-xs">
                  <RefreshCw size={14} className="text-amber-400 flex-shrink-0 mt-0.5" />
                  <span className="text-slate-400">{s}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ForecastTab({ forecast, campaignId, onForecast, loading, runAction }: {
  forecast: Forecast | null; campaignId: string;
  onForecast: () => Promise<void>;
  loading: boolean; runAction: (a: string, fn: () => Promise<unknown>) => void;
}) {
  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <button onClick={() => runAction("Forecast", onForecast)} disabled={loading}
          className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <TrendingUp size={14} />}
          Run LSTM Forecast (7-day)
        </button>
      </div>
      {!forecast ? (
        <div className="glass rounded-xl p-10 border border-surface-border text-center text-slate-500 text-sm">
          Click &quot;Run LSTM Forecast&quot; to generate engagement predictions.
        </div>
      ) : (
        <div className="glass-dynamic rounded-xl p-6 animate-scale-up">
          <h3 className="text-sm font-semibold text-brand-400 mb-4">LSTM Engagement Forecast — Next 7 Days</h3>
          <ForecastLineChart forecast={forecast} />
          <p className="text-xs text-slate-500 mt-3">Model: LSTM · Version: {forecast.model_version}</p>
        </div>
      )}
    </div>
  );
}

function OptimizeTab({ optimization, campaignId, onOptimize, loading, runAction }: {
  optimization: Optimization | null; campaignId: string;
  onOptimize: () => Promise<void>;
  loading: boolean; runAction: (a: string, fn: () => Promise<unknown>) => void;
}) {
  const scores = optimization?.platform_scores
    ? Object.entries(optimization.platform_scores).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <button onClick={() => runAction("Optimize", onOptimize)} disabled={loading}
          className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Target size={14} />}
          Run Campaign Optimizer
        </button>
      </div>
      {!optimization ? (
        <div className="glass rounded-xl p-10 border border-surface-border text-center text-slate-500 text-sm">
          Click &quot;Run Campaign Optimizer&quot; to get Thompson Sampling recommendations.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="glass-dynamic rounded-xl p-6 space-y-4 animate-fade-in-up">
            <h3 className="text-sm font-semibold text-brand-400 uppercase tracking-wide">Recommendations</h3>
            {[
              ["Best Platform", optimization.recommended_platform,                                             "text-brand-300"],
              ["Best Time",     optimization.recommended_time || "—",                                          "text-emerald-300"],
              ["Rec. Budget",   optimization.recommended_budget ? `$${optimization.recommended_budget}` : "—", "text-amber-300"],
              ["Confidence",    `${(optimization.confidence * 100).toFixed(1)}%`,                              "text-cyan-300"],
            ].map(([k, v, c]) => (
              <div key={k} className="flex justify-between items-center">
                <span className="text-xs text-slate-500">{k}</span>
                <span className={`text-sm font-semibold ${c}`}>{v}</span>
              </div>
            ))}
            {optimization.reasoning && (
              <p className="text-xs text-slate-400 border-t border-surface-border pt-3">
                {optimization.reasoning}
              </p>
            )}
          </div>
          <div className="glass-dynamic rounded-xl p-6 space-y-3 animate-fade-in-up delay-100">
            <h3 className="text-sm font-semibold text-brand-400 uppercase tracking-wide">Platform Scores</h3>
            {scores.map(([p, score]) => (
              <div key={p}>
                <div className="flex justify-between text-xs text-slate-400 mb-1">
                  <span>{p}</span><span>{score.toFixed(1)}</span>
                </div>
                <div className="h-2 bg-surface-muted rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-400"
                    style={{ width: `${Math.min(score, 100)}%`, transition: "width 0.5s ease" }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
