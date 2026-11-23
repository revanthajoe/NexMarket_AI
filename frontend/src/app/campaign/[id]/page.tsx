"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import toast from "react-hot-toast";
import dynamic from "next/dynamic";
import {
  Loader2, Image as ImageIcon, Send, TrendingUp,
  Target, Zap, RefreshCw, CheckCircle2, ChevronRight,
  AlertTriangle, Info,
} from "lucide-react";
import {
  api, invalidateCache, PIPELINE_STEPS, LANGUAGES,
  Campaign, Poster, PosterEvaluation, PosterFeedback, AdCopy,
  SocialPost, Forecast, Optimization, BrandKitInfo,
} from "@/lib/api";
import { AdCopyTab, PostingTab } from "@/components/campaign/CampaignTabs";
import { CampaignPipelineStatus, PipelineStage } from "@/components/campaign/CampaignPipelineStatus";
import { getPosterImageUrl, isMockPoster } from "@/lib/poster";

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
const MAX_POLL_MS = 25 * 60 * 1000;

const PIPELINE_STEP_LABELS: Record<string, string> = {
  poster: "Generating poster…",
  evaluate: "Evaluating poster…",
  adcopy: "Writing ad copy…",
  optimize: "Optimizing placement…",
  post: "Publishing to platforms…",
  analytics: "Collecting analytics…",
  sentiment: "Running sentiment analysis…",
  lead_prediction: "Scoring leads…",
  forecast: "Running LSTM forecast…",
  reward_sync: "Syncing rewards…",
};

const STATUS_BADGE: Record<string, string> = {
  draft:      "bg-slate-100 text-slate-600 border border-slate-200",
  generating: "bg-blue-100 text-blue-700 border border-blue-200",
  ready:      "bg-cyan-100 text-cyan-700 border border-cyan-200",
  posted:     "bg-emerald-100 text-emerald-700 border border-emerald-200",
  failed:     "bg-rose-100 text-rose-700 border border-rose-200",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${STATUS_BADGE[status] || STATUS_BADGE.draft}`}>
      {status}
    </span>
  );
}

const TABS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "overview",  label: "Overview",  icon: Info },
  { id: "poster",    label: "Poster",    icon: ImageIcon },
  { id: "adcopy",    label: "Ad Copy",   icon: Send },
  { id: "posting",   label: "Posting",   icon: Send },
  { id: "forecast",  label: "Forecast",  icon: TrendingUp },
  { id: "optimize",  label: "Optimize",  icon: Target },
];

// ── Mock/broken image fallback ────────────────────────────────────────────────
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
        className="w-full h-full min-h-[300px] bg-slate-50 border-2 border-dashed border-slate-200 rounded-xl
                   flex flex-col items-center justify-center gap-2 cursor-pointer
                   hover:bg-slate-100 transition-colors"
        onClick={onClick}
      >
        <ImageIcon size={32} className="text-slate-300" />
        <p className="text-sm font-semibold text-slate-600">Mock Provider</p>
        <p className="text-xs text-slate-400 text-center max-w-[200px]">
          No real image generated. Set IMAGE_PROVIDER=local to generate actual posters.
        </p>
      </div>
    );
  }

  if (errored) {
    return (
      <div
        className="w-full h-full min-h-[300px] bg-slate-50 border-2 border-dashed border-slate-200 rounded-xl
                   flex flex-col items-center justify-center gap-2 cursor-pointer
                   hover:bg-slate-100 transition-colors"
        onClick={onClick}
        title="Image failed to load"
      >
        <ImageIcon size={28} className="text-slate-300" />
        <p className="text-xs font-medium text-slate-400 text-center px-4">
          Image unavailable
        </p>
        <p className="text-[10px] text-slate-300 font-mono">provider: {provider}</p>
        <a href={resolvedSrc} target="_blank" rel="noreferrer"
          className="text-xs text-blue-500 underline mt-1"
          onClick={(e) => e.stopPropagation()}>
          Open directly ↗
        </a>
      </div>
    );
  }

  return (
    <div
      className="w-full h-full bg-white border border-slate-200 rounded-xl overflow-hidden
                 relative group cursor-pointer"
      onClick={onClick}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={resolvedSrc}
        alt={alt}
              width={1080}
              height={1350}
        loading="lazy"
        decoding="async"
        onError={() => setErrored(true)}
        className="w-full h-full object-contain transition-transform duration-300 group-hover:scale-105"
      />
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors duration-200
                      flex items-center justify-center">
        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-white text-xs
                         font-medium bg-black/50 px-3 py-1.5 rounded-lg">
          Click to preview
        </span>
      </div>
    </div>
  );
}

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [campaign, setCampaign]           = useState<Campaign | null>(null);
  const [posters, setPosters]             = useState<Poster[]>([]);
  const [evaluations, setEvaluations]     = useState<Record<string, PosterEvaluation>>({});
  const [feedback, setFeedback]           = useState<PosterFeedback[]>([]);
  const [copies, setCopies]               = useState<AdCopy[]>([]);
  const [posts, setPosts]                 = useState<SocialPost[]>([]);
  const [selectedPosterId, setSelectedPosterId] = useState<string | null>(null);
  const [forecast, setForecast]           = useState<Forecast | null>(null);
  const [optimization, setOptimization]   = useState<Optimization | null>(null);
  const [tab, setTab]                     = useState<TabId>("overview");
  const [loading, setLoading]             = useState(true);
  const [actionLoading, setActionLoading] = useState("");
  const [regeneratingPosterId, setRegeneratingPosterId] = useState<string | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null);
  const [pipelineStep, setPipelineStep]   = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [resourceErrors, setResourceErrors] = useState<Record<string, string>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    setResourceErrors({});
    try {
      const [c, ps, ads, sps] = await Promise.all([
        api.campaigns.get(id),
        api.posters.getByCampaign(id).catch((err: unknown) => {
          setResourceErrors((current) => ({
            ...current,
            posters: err instanceof Error ? err.message : "Failed to load posters.",
          }));
          return [] as Poster[];
        }),
        api.adcopy.getByCampaign(id).catch((err: unknown) => {
          setResourceErrors((current) => ({
            ...current,
            "ad copy": err instanceof Error ? err.message : "Failed to load ad copy.",
          }));
          return [] as AdCopy[];
        }),
        api.posting.getBycampaign(id).catch((err: unknown) => {
          setResourceErrors((current) => ({
            ...current,
            posts: err instanceof Error ? err.message : "Failed to load publish history.",
          }));
          return [] as SocialPost[];
        }),
      ]);
      const realPosters = ps.filter((poster) => !isMockPoster(poster.provider));
      setCampaign(c); setPosters(realPosters); setCopies(ads); setPosts(sps);
      const loadedEvaluations = await Promise.all(realPosters.map(async (poster) => {
        const rows = await api.posters.getEvaluations(poster.id).catch((err: unknown) => {
          setResourceErrors((current) => ({
            ...current,
            evaluations: err instanceof Error ? err.message : "Failed to load poster evaluations.",
          }));
          return [] as PosterEvaluation[];
        });
        return [poster.id, rows[rows.length - 1]] as const;
      }));
      setEvaluations(Object.fromEntries(loadedEvaluations.filter(([, evaluation]) => evaluation)) as Record<string, PosterEvaluation>);
      const latestPoster = realPosters[realPosters.length - 1];
      setSelectedPosterId((current) => current && realPosters.some((poster) => poster.id === current)
        ? current
        : latestPoster?.id ?? null);
      if (latestPoster) {
        const posterFeedback = await api.posters.getFeedback(latestPoster.id).catch((err: unknown) => {
          setResourceErrors((current) => ({
            ...current,
            feedback: err instanceof Error ? err.message : "Failed to load poster feedback.",
          }));
          return [] as PosterFeedback[];
        });
        setFeedback(posterFeedback);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load campaign";
      setLoadError(message);
      setCampaign(null);
      toast.error("Failed to load campaign");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const runAction = useCallback(async (action: string, fn: () => Promise<unknown>) => {
    setActionLoading(action);
    try {
      await fn();
      if (action !== "Poster Generation") await load();
      toast.success(`${action} complete!`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`${action} failed: ${msg}`);
    } finally {
      setActionLoading("");
    }
  }, [load]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const runPipeline = useCallback(async () => {
    setActionLoading("Full Pipeline");
    setPipelineStatus("generating");
    setPipelineStep("Starting pipeline…");
    try {
      await api.n8n.trigger(id, PIPELINE_STEPS, true);
    } catch (err: unknown) {
      setActionLoading("");
      setPipelineStatus(null);
      setPipelineStep("");
      toast.error(`Failed to start pipeline: ${err instanceof Error ? err.message : String(err)}`);
      return;
    }

    stopPolling();
    const startedAt = Date.now();
    let stepIdx = 0;
    const steps = PIPELINE_STEPS;

    pollRef.current = setInterval(async () => {
      // Cycle through step labels to give user feedback
      setPipelineStep(PIPELINE_STEP_LABELS[steps[stepIdx % steps.length]] || "Processing…");
      stepIdx++;

      let snapshot;
      try {
        snapshot = await api.n8n.status(id);
      } catch {
        return;
      }
      setPipelineStatus(snapshot.status);

      if (snapshot.status === "generating") {
        if (Date.now() - startedAt > MAX_POLL_MS) {
          stopPolling();
          setActionLoading("");
          setPipelineStatus(null);
          setPipelineStep("");
          toast.error("Still generating after 25 minutes — check the backend, then refresh.");
        }
        return;
      }

      stopPolling();
      setActionLoading("");
      setPipelineStatus(null);
      setPipelineStep("");
      invalidateCache();
      await load();
      if (snapshot.status === "failed") {
        toast.error("Pipeline failed — check the backend logs.");
      } else {
        toast.success("Pipeline complete!");
      }
    }, POLL_INTERVAL_MS);
  }, [id, load, stopPolling]);

  if (loading) {
    return (
      <div className="space-y-4 animate-fade-in">
        <div className="bg-white border border-slate-200 rounded-2xl p-6 h-28 shimmer" />
        <div className="bg-white border border-slate-200 rounded-2xl p-5 h-40 shimmer" />
        <div className="bg-white border border-slate-200 rounded-2xl p-6 h-64 shimmer" />
      </div>
    );
  }
  if (!campaign) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-10 text-center">
        <AlertTriangle size={32} className="text-amber-400 mx-auto mb-3" />
        <p className="text-slate-700 font-medium">
          {loadError ? "Unable to load campaign" : "Campaign not found"}
        </p>
        <p className="text-slate-400 text-sm mt-1">
          {loadError || "Check the URL or go back to campaigns."}
        </p>
        <div className="flex justify-center gap-3 mt-5">
          {loadError && (
            <button onClick={() => { setLoading(true); void load(); }}
              className="px-4 py-2 rounded-lg text-sm font-semibold border border-slate-200 text-slate-700 hover:bg-slate-50">
              Retry
            </button>
          )}
          <a href="/campaigns" className="btn-brand px-4 py-2 rounded-lg text-sm font-semibold">
            Back to campaigns
          </a>
        </div>
      </div>
    );
  }

  const hasPoster = posters.length > 0;
  const hasEvaluation = Object.keys(evaluations).length > 0;
  const hasAdCopy = copies.length > 0;
  const hasPublishedPost = posts.some((post) => post.status === "posted");
  const hasPendingPost = posts.some((post) => ["pending", "posting", "scheduled"].includes(post.status));

  const pipelineStages: PipelineStage[] = [
    { label: "Create",   state: "complete",                                                                                    note: "saved" },
    { label: "Generate", state: hasPoster ? "complete" : campaign.status === "generating" ? "active" : "pending" },
    { label: "Evaluate", state: hasEvaluation || posters.length > 1 || hasPublishedPost || hasPendingPost ? "complete" : hasPoster ? "pending" : "unavailable" },
    { label: "Improve",  state: posters.length > 1 || hasPublishedPost || hasPendingPost ? "complete" : "pending", note: posters.length > 1 ? `${posters.length} versions` : "optional" },
    { label: "Publish",  state: hasPublishedPost ? "complete" : hasPendingPost ? "active" : "pending" },
    { label: "Observe",  state: "pending", note: "ACTUAL data only" },
    { label: "Analyze",  state: "pending", note: "awaiting data" },
    { label: "Predict",  state: "pending", note: "PREDICTED" },
    { label: "Optimize", state: "pending", note: "RECOMMENDATION" },
    { label: "Reward",   state: "pending", note: "ACTUAL required" },
  ];

  return (
    <div className="space-y-5">
      {Object.keys(resourceErrors).length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm" role="alert">
          <div className="flex items-start justify-between gap-4">
            <div className="flex gap-2">
              <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-900">Some campaign data could not be loaded</p>
                <ul className="mt-1 space-y-1 text-amber-800">
                  {Object.entries(resourceErrors).map(([resource, message]) => (
                    <li key={resource}>
                      <span className="font-medium capitalize">{resource}:</span> {message}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <button onClick={() => { void load(); }}
              className="shrink-0 px-3 py-1.5 rounded-lg border border-amber-300 bg-white text-amber-800 text-xs font-semibold hover:bg-amber-100">
              Retry
            </button>
          </div>
        </div>
      )}
      {/* ── Campaign header ─────────────────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 animate-fade-in-up">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3 mb-1.5 flex-wrap">
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">{campaign.name}</h1>
              <StatusBadge status={campaign.status} />
            </div>
            <p className="text-sm text-slate-500">
              {campaign.product_name} · {campaign.campaign_goal.replace(/_/g, " ")} · {campaign.preferred_platform}
            </p>
          </div>
          <button
            onClick={runPipeline}
            disabled={!!actionLoading}
            className="btn-brand px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 shrink-0"
          >
            {actionLoading === "Full Pipeline" ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Zap size={14} />
            )}
            {actionLoading === "Full Pipeline" ? "Running…" : "Run Pipeline"}
          </button>
        </div>

        {/* Pipeline progress feedback */}
        {pipelineStatus && (
          <div className="mt-4 pt-4 border-t border-slate-100">
            <div className="flex items-center gap-2 text-sm text-slate-600 mb-2">
              <Loader2 size={13} className="animate-spin text-blue-500 flex-shrink-0" />
              <span className="font-medium">{pipelineStep || "Pipeline running…"}</span>
              <span className="text-slate-400 text-xs ml-auto">Takes several minutes</span>
            </div>
            <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full
                              animate-pulse" style={{ width: "60%" }} />
            </div>
          </div>
        )}
      </div>

      {/* ── Pipeline stages ─────────────────────────────────────────────── */}
      <CampaignPipelineStatus stages={pipelineStages} />

      {/* ── Tabs ────────────────────────────────────────────────────────── */}
      <div className="border-b border-slate-200 -mb-2">
        <div className="flex gap-1 overflow-x-auto pb-px">
          {TABS.map(({ id: tid, label, icon: Icon }) => (
            <button
              key={tid}
              onClick={() => setTab(tid)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                tab === tid
                  ? "text-blue-700 border-blue-600 bg-blue-50/50"
                  : "text-slate-500 border-transparent hover:text-slate-800 hover:border-slate-300"
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Tab content ─────────────────────────────────────────────────── */}
      <div className="animate-fade-in-up">
        {tab === "overview" && <OverviewTab campaign={campaign} copies={copies} posts={posts} />}
        {tab === "poster" && (
          <PosterTab
            posters={posters} evaluations={evaluations} selectedPosterId={selectedPosterId}
            onSelect={setSelectedPosterId} feedback={feedback} campaignId={id}
            onGenerate={(language: string) => runAction("Poster Generation", async () => {
              const p = await api.posters.generate(id, 2, language);
              setPosters((prev) => [
                ...p.filter((poster) => !isMockPoster(poster.provider)),
                ...prev.filter((poster) => !isMockPoster(poster.provider)),
              ]);
              const generatedEvaluations = await Promise.all(p.map(async (poster) => {
                try {
                  return [poster.id, await api.posters.evaluate(poster.id)] as const;
                } catch (evErr) {
                  console.warn("[PosterTab] Evaluation failed, continuing:", evErr);
                  return null;
                }
              }));
              setEvaluations((current) => ({
                ...current,
                ...Object.fromEntries(generatedEvaluations.filter((item): item is readonly [string, PosterEvaluation] => item !== null)),
              }));
              setSelectedPosterId(p[0]?.id ?? null);
            })}
            loading={actionLoading === "Poster Generation"}
            onRegenerate={async (posterId: string) => {
              setRegeneratingPosterId(posterId);
              setActionLoading("Poster Regeneration");
              try {
                const regenerated = await api.posters.regenerate(posterId);
                setPosters((prev) => [...prev, regenerated]);
                const [evaluations, posterFeedback] = await Promise.all([
                  api.posters.getEvaluations(regenerated.id),
                  api.posters.getFeedback(regenerated.id),
                ]);
                setEvaluations((current) => ({ ...current, [regenerated.id]: evaluations[evaluations.length - 1] }));
                setFeedback(posterFeedback);
                toast.success(`Poster version ${regenerated.version} generated`);
              } catch (err: unknown) {
                toast.error(`Poster regeneration failed: ${err instanceof Error ? err.message : String(err)}`);
              } finally {
                setRegeneratingPosterId(null);
                setActionLoading("");
              }
            }}
            regeneratingPosterId={regeneratingPosterId}
          />
        )}
        {tab === "adcopy" && (
          <AdCopyTab copies={copies} campaignId={id}
            onGenerate={(platforms: string[], tone: string, language: string) =>
              runAction("Ad Copy", async () => {
                const fresh = await api.adcopy.generate(id, platforms, tone, language);
                setCopies((prev) => [...prev, ...fresh]);
              })}
            loading={actionLoading === "Ad Copy"}
          />
        )}
        {tab === "posting" && (
          <PostingTab posts={posts} campaignId={id} copies={copies} posters={posters}
            selectedPosterId={selectedPosterId}
            onPost={(platforms, ad_copy_id, poster_id) =>
              runAction("Post", () => api.posting.publishCampaign(id, { platforms, ad_copy_id, poster_id }))
            }
            loading={actionLoading === "Post"}
          />
        )}
        {tab === "forecast" && (
          <ForecastTab forecast={forecast} campaignId={id}
            onForecast={async () => { const f = await api.forecast.create(id, 7); setForecast(f); }}
            loading={actionLoading === "Forecast"}
            runAction={runAction}
          />
        )}
        {tab === "optimize" && (
          <OptimizeTab optimization={optimization} campaignId={id}
            onOptimize={async () => { const o = await api.optimize.run(id, campaign.budget || 500); setOptimization(o); }}
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
  const fields = [
    ["Product",     campaign.product_name],
    ["Description", campaign.description],
    ["Offer",       campaign.offer],
    ["Target",      campaign.target_audience],
    ["Goal",        campaign.campaign_goal.replace(/_/g, " ")],
    ["Platform",    campaign.preferred_platform],
    ["Budget",      campaign.budget ? `$${campaign.budget}` : "Not set"],
  ];

  const POST_STATUS_COLORS: Record<string, string> = {
    posted:  "bg-emerald-100 text-emerald-700",
    failed:  "bg-rose-100 text-rose-700",
    pending: "bg-amber-100 text-amber-700",
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      {/* Campaign details */}
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-xs font-semibold text-blue-600 uppercase tracking-widest mb-4">Campaign Details</h3>
        <div className="space-y-3">
          {fields.map(([k, v]) => (
            <div key={k} className="flex gap-4">
              <span className="text-xs text-slate-400 w-24 flex-shrink-0 pt-0.5">{k}</span>
              <span className="text-sm text-slate-700 min-w-0">{v}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        {/* Posts */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h3 className="text-xs font-semibold text-blue-600 uppercase tracking-widest mb-3">Published Posts</h3>
          {posts.length === 0 ? (
            <p className="text-sm text-slate-400 italic">No posts published yet</p>
          ) : (
            <div className="space-y-2">
              {posts.map((p) => (
                <div key={p.id} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
                  <span className="text-sm text-slate-700 capitalize">{p.platform}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${POST_STATUS_COLORS[p.status] || "bg-slate-100 text-slate-600"}`}>
                    {p.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Ad copies summary */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h3 className="text-xs font-semibold text-blue-600 uppercase tracking-widest mb-2">Ad Copies</h3>
          {copies.length === 0 ? (
            <p className="text-sm text-slate-400 italic">No ad copy generated yet</p>
          ) : (
            <p className="text-sm text-slate-600">
              {copies.length} platform variant{copies.length !== 1 ? "s" : ""} generated
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function PosterTab({ posters, evaluations, selectedPosterId, onSelect, feedback, campaignId, onGenerate, onRegenerate, loading, regeneratingPosterId }: {
  posters: Poster[]; evaluations: Record<string, PosterEvaluation>; selectedPosterId: string | null;
  onSelect: (posterId: string) => void; feedback: PosterFeedback[]; campaignId: string;
  onGenerate: (language: string) => void;
  onRegenerate: (posterId: string) => Promise<void>;
  loading: boolean; regeneratingPosterId: string | null;
}) {
  const [lightbox, setLightbox]   = useState<string | null>(null);
  const [brandKit, setBrandKit]   = useState<BrandKitInfo | null>(null);
  const [kitLoading, setKitLoad]  = useState(false);
  const [language, setLanguage]   = useState("en");
  const [brandColor, setBrandColor] = useState("");
  const [showKit, setShowKit]     = useState(false);
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
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm"
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
              <span className="text-lg leading-none">✕</span> Close
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={lightbox}
              alt="Poster preview"
              className="w-full h-auto max-h-[85vh] object-contain rounded-2xl shadow-2xl border border-white/10"
            />
            <div className="mt-3 flex justify-center gap-6">
              <a href={lightbox} target="_blank" rel="noreferrer"
                className="text-xs text-blue-400 hover:text-blue-300 underline"
                onClick={(e) => e.stopPropagation()}>
                Open in new tab ↗
              </a>
              <a href={lightbox} download
                className="text-xs text-emerald-400 hover:text-emerald-300 underline"
                onClick={(e) => e.stopPropagation()}>
                Download ↓
              </a>
            </div>
          </div>
        </div>
      )}

      {/* ── Brand Kit Panel ──────────────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <button
          onClick={() => { setShowKit((v) => !v); if (!showKit) loadKit(); }}
          className="w-full flex items-center justify-between px-5 py-3.5 text-sm font-medium
                     text-slate-700 hover:bg-slate-50 transition-colors"
        >
          <span className="flex items-center gap-2">
            <span>🎨</span>
            <span>Brand Kit — Assets · Contact · Language · Brand Colour</span>
            {brandKit && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                brandKit.layout === "brochure" ? "bg-emerald-100 text-emerald-700" : "bg-blue-100 text-blue-700"
              }`}>
                {brandKit.layout === "brochure" ? "Brochure" : "Designed"}
              </span>
            )}
          </span>
          <span className="text-slate-400 text-xs">{showKit ? "▲ Collapse" : "▼ Expand"}</span>
        </button>
        {showKit && (
          <div className="px-5 pb-5 pt-2 border-t border-slate-100 grid grid-cols-1 md:grid-cols-2 gap-4">
            {brandKit && (
              <div className="md:col-span-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs text-slate-600">
                  Layout:{" "}
                  <span className={`font-semibold ${brandKit.layout === "brochure" ? "text-emerald-700" : "text-blue-700"}`}>
                    {brandKit.layout === "brochure" ? "Full brochure" : "Designed poster"}
                  </span>
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {brandKit.layout === "brochure"
                    ? "All zones render, including the contact footer."
                    : "Add a product cutout + phone/address to unlock the contact footer."}
                </p>
              </div>
            )}

            {/* Asset uploads */}
            {([
              { type: "logo",           label: "Brand Logo",      hint: "header band" },
              { type: "partner_logo",   label: "Partner Logo",    hint: "optional, header right" },
              { type: "product_cutout", label: "Product Cutout",  hint: "transparent PNG — best hero" },
              { type: "product",        label: "Product Image",   hint: "used if no cutout" },
              { type: "map_image",      label: "Map / Location",  hint: "contact footer thumbnail" },
              { type: "font_bold",      label: "Font (Bold)",     hint: "optional" },
              { type: "font_regular",   label: "Font (Regular)",  hint: "optional" },
            ] as const).map(({ type, label, hint }) => (
              <div key={type} className="space-y-1">
                <label htmlFor={`file-upload-${type}`} className="block text-xs text-slate-600 font-medium cursor-pointer">
                  {label} <span className="text-slate-400">({hint})</span>
                </label>
                <input
                  type="file" disabled={kitLoading}
                  id={`file-upload-${type}`} name={`file-upload-${type}`}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFile(type, f); }}
                  className="block w-full text-xs text-slate-500 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg
                             file:border-0 file:bg-blue-50 file:text-blue-700 file:text-xs file:font-medium cursor-pointer"
                />
                {brandKit?.[type as keyof BrandKitInfo] && (
                  <p className="text-[10px] text-emerald-600">✓ uploaded</p>
                )}
              </div>
            ))}

            {/* Contact details */}
            {([
              { key: "phone",      label: "Phone",             placeholder: "+91 98765 43210" },
              { key: "website",    label: "Website",           placeholder: "example.com" },
              { key: "address_en", label: "Address (English)", placeholder: "12 Main Road, Coimbatore" },
              { key: "address_ta", label: "Address (Local)",   placeholder: "local-language address" },
            ] as const).map(({ key, label, placeholder }) => (
              <div key={key} className="space-y-1">
                <label htmlFor={`contact-${key}`} className="block text-xs text-slate-600 font-medium">{label}</label>
                <input
                  type="text" id={`contact-${key}`} name={`contact-${key}`}
                  value={contact[key]} placeholder={placeholder}
                  onChange={(e) => setContact((c) => ({ ...c, [key]: e.target.value }))}
                  className="input-dark text-xs"
                />
              </div>
            ))}

            {/* Language */}
            <div className="space-y-1">
              <label htmlFor="poster-language" className="block text-xs text-slate-600 font-medium">Poster Language</label>
              <select
                id="poster-language" name="poster-language"
                value={language} onChange={(e) => setLanguage(e.target.value)}
                className="input-dark text-sm"
              >
                {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>

            {/* Brand Colour */}
            <div className="space-y-1">
              <label htmlFor="brand-color" className="block text-xs text-slate-600 font-medium">Brand Colour (CTA Button)</label>
              <div className="flex gap-3 items-center">
                <input
                  type="color" value={brandColor || "#dc2626"}
                  id="brand-color" name="brand-color"
                  onChange={(e) => setBrandColor(e.target.value)}
                  className="h-8 w-10 rounded cursor-pointer border border-slate-200 bg-transparent"
                />
                <span className="text-xs text-slate-400 font-mono">{brandColor || "#dc2626"}</span>
              </div>
            </div>

            <div className="md:col-span-2 flex justify-end">
              <button onClick={saveMeta} disabled={kitLoading}
                className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2">
                {kitLoading ? <Loader2 size={13} className="animate-spin" /> : null}
                Save Brand Settings
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Generate button ──────────────────────────────────────────── */}
      <div className="flex justify-between items-center">
        <span className="text-sm text-slate-500">
          Language: <span className="font-medium text-slate-700">{LANGUAGES.find((l) => l.code === language)?.label ?? language}</span>
        </span>
        <button
          onClick={() => onGenerate(language)}
          disabled={loading}
          className="btn-brand px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Generate Posters + Evaluate
        </button>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-8 text-center space-y-4">
          <Loader2 size={28} className="animate-spin text-blue-500 mx-auto" />
          <div>
            <p className="text-sm font-semibold text-blue-800">Multi-Stage AI Pipeline Running…</p>
            <p className="text-xs text-blue-600 mt-1">Keep this tab visible — browser may suspend background tabs.</p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            {["🧠 Qwen LLM", "🎨 SDXL Generate", "🖼️ Composer", "🔍 Qwen VL"].map((s, i) => (
              <span key={i} className="text-xs px-3 py-1 rounded-full bg-blue-100 text-blue-700 border border-blue-200 font-medium">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Posters list */}
      {!loading && posters.length === 0 && (
        <div className="bg-white border-2 border-dashed border-slate-200 rounded-xl p-12 text-center">
          <ImageIcon size={32} className="text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">No posters yet.</p>
          <p className="text-slate-400 text-xs mt-1">Click &quot;Generate Posters + Evaluate&quot; to create AI-generated marketing visuals.</p>
        </div>
      )}

      {!loading && posters.length > 0 && (
        <div className="space-y-5">
          {posters.map((p, i) => (
            <div
              key={p.id}
              className="bg-white border border-slate-200 rounded-xl overflow-hidden p-5 animate-fade-in-up"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              {/* Version header */}
              <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-white bg-blue-600 px-2.5 py-1 rounded-md">
                    V{p.version}
                  </span>
                  <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                    <input
                      type="radio"
                      name="selected-poster-version"
                      checked={selectedPosterId === p.id}
                      onChange={() => onSelect(p.id)}
                      aria-label={`Select poster version ${p.version}`}
                    />
                    Version {p.version}
                  </label>
                  {evaluations[p.id] && (
                    <span className="text-xs text-slate-500">Score: {evaluations[p.id].overall_score}/100</span>
                  )}
                  {p.parent_poster_id && (
                    <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
                      {p.generation_reason === "pipeline_regeneration" ? "Pipeline refresh" : "Regenerated from feedback"}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 font-mono">provider: {p.provider}</span>
                  <button
                    onClick={() => onRegenerate(p.id)}
                    disabled={!!regeneratingPosterId}
                    className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1.5
                               disabled:opacity-50 font-medium border border-blue-200 bg-blue-50
                               hover:bg-blue-100 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    {regeneratingPosterId === p.id ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                    Regenerate
                  </button>
                </div>
              </div>

              {/* Image(s) */}
              <div className="flex flex-col md:flex-row gap-4 items-start">
                {p.metadata_?.visual_url && (
                  <>
                    <div className="flex-1 w-full space-y-2">
                      <p className="text-xs text-slate-500 font-medium text-center">Generated Visual (SDXL)</p>
                      <PosterImage
                        src={p.metadata_.visual_url}
                        provider={p.provider}
                        alt="Generated Visual"
                        onClick={() => setLightbox(p.metadata_!.visual_url!)}
                      />
                    </div>
                    <div className="hidden md:flex flex-col items-center justify-center px-2 text-slate-300 self-center">
                      <ChevronRight size={20} />
                      <span className="text-[10px] text-slate-400 mt-1">Composer</span>
                    </div>
                  </>
                )}
                <div className="flex-1 w-full space-y-2">
                  <p className="text-xs text-blue-600 font-semibold text-center">Final Marketing Poster</p>
                  <PosterImage
                    src={p.image_url}
                    provider={p.provider}
                    alt={`Final Poster V${p.version}`}
                    onClick={() => setLightbox(p.image_url)}
                  />
                </div>
              </div>

              {p.improvement_instruction && (
                <p className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  Improvement: {p.improvement_instruction}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Evaluation */}
      {selectedPosterId && evaluations[selectedPosterId] && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 mt-4 animate-fade-in-up">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-800">
              Vision AI Evaluation Score
            </h3>
            <span className={`text-xl font-bold ${
              evaluations[selectedPosterId].overall_score >= 80 ? "text-emerald-600" :
              evaluations[selectedPosterId].overall_score >= 60 ? "text-amber-600" : "text-rose-600"
            }`}>
              {evaluations[selectedPosterId].overall_score}<span className="text-sm text-slate-400">/100</span>
            </span>
          </div>
          <div className="text-[10px] uppercase tracking-widest text-slate-400 mb-4">
            {evaluations[selectedPosterId].source_type || "UNKNOWN"}{evaluations[selectedPosterId].is_fallback ? " · FALLBACK" : ""}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <PosterRadarChart eval_={evaluations[selectedPosterId]} />
            <div className="space-y-2.5">
              {evaluations[selectedPosterId].strengths?.map((s, i) => (
                <div key={i} className="flex gap-2.5 text-sm">
                  <CheckCircle2 size={15} className="text-emerald-500 flex-shrink-0 mt-0.5" />
                  <span className="text-slate-600">{s}</span>
                </div>
              ))}
              {evaluations[selectedPosterId].suggestions?.map((s, i) => (
                <div key={i} className="flex gap-2.5 text-sm">
                  <RefreshCw size={15} className="text-amber-500 flex-shrink-0 mt-0.5" />
                  <span className="text-slate-500">{s}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {feedback.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 animate-fade-in-up">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Available Feedback</h3>
          <div className="space-y-2">
            {feedback.map((item) => (
              <div key={item.id} className="flex justify-between gap-3 text-sm py-2 border-b border-slate-100 last:border-0">
                <span className="text-slate-600">{item.feedback_text}</span>
                <span className="text-xs text-slate-400 shrink-0 pt-0.5">{item.source_type}</span>
              </div>
            ))}
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
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-base font-semibold text-slate-800">LSTM Engagement Forecast</h3>
          <p className="text-xs text-slate-500 mt-0.5">Requires ≥14 ACTUAL historical observations</p>
        </div>
        <button
          onClick={() => runAction("Forecast", onForecast)}
          disabled={loading}
          className="btn-brand px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <TrendingUp size={14} />}
          Run LSTM Forecast (7-day)
        </button>
      </div>

      {!forecast ? (
        <div className="bg-white border-2 border-dashed border-slate-200 rounded-xl p-12 text-center">
          <TrendingUp size={28} className="text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">Click &quot;Run LSTM Forecast&quot; to generate engagement predictions.</p>
          <p className="text-slate-400 text-xs mt-1">
            Forecast requires at least 14 days of ACTUAL analytics data from a live platform.
          </p>
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl p-6 animate-scale-up">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-800">Next 7 Days — LSTM Prediction</h3>
            <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
              {forecast.source_type || "FORECAST"}
            </span>
          </div>
          <ForecastLineChart forecast={forecast} />
          <p className="text-xs text-slate-400 mt-3 font-mono">
            Model: {forecast.model_version} · History: {forecast.history_source || "UNKNOWN"}
          </p>
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
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-base font-semibold text-slate-800">Campaign Optimizer</h3>
          <p className="text-xs text-slate-500 mt-0.5">Thompson Sampling contextual bandit recommendation</p>
        </div>
        <button
          onClick={() => runAction("Optimize", onOptimize)}
          disabled={loading}
          className="btn-brand px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Target size={14} />}
          Run Campaign Optimizer
        </button>
      </div>

      {!optimization ? (
        <div className="bg-white border-2 border-dashed border-slate-200 rounded-xl p-12 text-center">
          <Target size={28} className="text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">Click &quot;Run Campaign Optimizer&quot; to get Thompson Sampling recommendations.</p>
          <p className="text-slate-400 text-xs mt-1">
            Algorithm: Thompson Sampling contextual multi-armed bandit — not generic RL.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Recommendations */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 animate-fade-in-up">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-800">Recommendations</h3>
              <span className="text-xs text-blue-600 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full font-medium">
                {optimization.source_type || "RECOMMENDATION"}
              </span>
            </div>
            {[
              ["Best Platform", optimization.recommended_platform,                                             "text-blue-700"],
              ["Best Time",     optimization.recommended_time || "—",                                          "text-emerald-700"],
              ["Rec. Budget",   optimization.recommended_budget ? `$${optimization.recommended_budget}` : "—", "text-amber-700"],
              ["Confidence",    `${(optimization.confidence * 100).toFixed(1)}%`,                              "text-slate-700"],
            ].map(([k, v, c]) => (
              <div key={k} className="flex justify-between items-center py-2 border-b border-slate-100 last:border-0">
                <span className="text-sm text-slate-500">{k}</span>
                <span className={`text-sm font-semibold ${c}`}>{v}</span>
              </div>
            ))}
            {optimization.reasoning && (
              <p className="text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2.5 leading-relaxed border border-slate-200">
                {optimization.reasoning}
              </p>
            )}
            <div className="text-[10px] text-slate-400 pt-1">
              Algorithm: {optimization.algorithm || "Thompson Sampling"} · Policy: {optimization.policy_version || "—"}
            </div>
          </div>

          {/* Platform scores */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 animate-fade-in-up">
            <h3 className="text-sm font-semibold text-slate-800">Platform Scores</h3>
            {scores.length === 0 ? (
              <p className="text-sm text-slate-400 italic">No platform scores available</p>
            ) : scores.map(([p, score]) => (
              <div key={p}>
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="text-slate-700 capitalize">{p}</span>
                  <span className="text-slate-500 font-mono text-xs">{score.toFixed(1)}</span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400"
                    style={{ width: `${Math.min(score, 100)}%`, transition: "width 0.6s ease" }}
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
