"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import toast from "react-hot-toast";
import dynamic from "next/dynamic";
import {
  Loader2, Image as ImageIcon, Send, TrendingUp,
  Target, Zap, RefreshCw, CheckCircle2,
} from "lucide-react";
import {
  api, Campaign, Poster, PosterEvaluation, AdCopy,
  SocialPost, Forecast, Optimization,
} from "@/lib/api";

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

  const load = async () => {
    try {
      const [c, ps, ads, sps] = await Promise.all([
        api.campaigns.get(id),
        api.posters.generate(id, 1).catch(() => [] as Poster[]),
        api.adcopy.getByCampaign(id).catch(() => [] as AdCopy[]),
        api.posting.getBycampaign(id).catch(() => [] as SocialPost[]),
      ]);
      setCampaign(c); setPosters(ps); setCopies(ads); setPosts(sps);
    } catch {
      toast.error("Failed to load campaign");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const runAction = async (action: string, fn: () => Promise<unknown>) => {
    setActionLoading(action);
    try {
      await fn();
      await load();
      toast.success(`${action} complete!`);
    } catch {
      toast.error(`${action} failed`);
    } finally {
      setActionLoading("");
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 size={32} className="animate-spin text-brand-400" />
    </div>
  );
  if (!campaign) return <p className="text-slate-500">Campaign not found.</p>;

  const StatusBadge = ({ status }: { status: string }) => {
    const map: Record<string, string> = {
      draft: "badge-pending", generating: "badge-pending", ready: "badge-mock",
      posted: "badge-posted", failed: "badge-failed",
    };
    return (
      <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${map[status] || "badge-pending"}`}>
        {status}
      </span>
    );
  };

  const TABS: { id: TabId; label: string; icon: React.ElementType }[] = [
    { id: "overview",  label: "Overview",  icon: Zap },
    { id: "poster",    label: "Poster",    icon: ImageIcon },
    { id: "adcopy",    label: "Ad Copy",   icon: Send },
    { id: "posting",   label: "Posting",   icon: Send },
    { id: "forecast",  label: "Forecast",  icon: TrendingUp },
    { id: "optimize",  label: "Optimize",  icon: Target },
  ];

  return (
    <div className="space-y-6">
      {/* Campaign Header */}
      <div className="glass rounded-2xl p-6 border border-surface-border">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-xl font-bold text-white">{campaign.name}</h1>
              <StatusBadge status={campaign.status} />
            </div>
            <p className="text-sm text-slate-400">{campaign.product_name} · {campaign.campaign_goal} · {campaign.preferred_platform}</p>
          </div>
          <button
            onClick={() => runAction("Full Pipeline", () => api.n8n.trigger(id))}
            disabled={!!actionLoading}
            className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2"
          >
            {actionLoading === "Full Pipeline" ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            Run Pipeline
          </button>
        </div>
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
      {tab === "overview" && <OverviewTab campaign={campaign} copies={copies} posts={posts} />}
      {tab === "poster" && (
        <PosterTab
          posters={posters} eval_={eval_} campaignId={id}
          onGenerate={() => runAction("Poster Generation", async () => {
            const p = await api.posters.generate(id, 2);
            setPosters(p);
            if (p[0]) {
              const ev = await api.posters.evaluate(p[0].id);
              setEval(ev);
            }
          })}
          loading={actionLoading === "Poster Generation"}
        />
      )}
      {tab === "adcopy" && (
        <AdCopyTab copies={copies} campaignId={id}
          onGenerate={() => runAction("Ad Copy", async () => {
            const c = await api.adcopy.generate(id, ["instagram","facebook","linkedin","twitter","email"]);
            setCopies(c);
          })}
          loading={actionLoading === "Ad Copy"}
        />
      )}
      {tab === "posting" && (
        <PostingTab posts={posts} campaignId={id} copies={copies} posters={posters}
          onPost={(platform, ad_copy_id, poster_id) =>
            runAction("Post", () => api.posting.publish({ campaign_id: id, platform, ad_copy_id, poster_id }))
          }
          loading={actionLoading === "Post"}
        />
      )}
      {tab === "forecast" && (
        <ForecastTab forecast={forecast} campaignId={id}
          onForecast={async () => {
            await api.analytics.seedDemo(id);
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
  );
}

// ── Sub-tabs ──────────────────────────────────────────────────────────────────

function OverviewTab({ campaign, copies, posts }: {
  campaign: Campaign; copies: AdCopy[]; posts: SocialPost[];
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="glass rounded-xl p-5 border border-surface-border space-y-3">
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
        <div className="glass rounded-xl p-5 border border-surface-border">
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
        <div className="glass rounded-xl p-5 border border-surface-border">
          <h3 className="text-sm font-semibold text-brand-400 uppercase tracking-wide mb-3">Ad Copies</h3>
          <p className="text-xs text-slate-400">{copies.length} platform variant{copies.length !== 1 ? "s" : ""} generated</p>
        </div>
      </div>
    </div>
  );
}

function PosterTab({ posters, eval_, campaignId, onGenerate, loading }: {
  posters: Poster[]; eval_: PosterEvaluation | null; campaignId: string;
  onGenerate: () => void; loading: boolean;
}) {
  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <button onClick={onGenerate} disabled={loading}
          className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Generate Posters + Evaluate
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {posters.slice(0, 2).map((p) => (
          <div key={p.id} className="glass rounded-xl overflow-hidden border border-surface-border">
            <div className="aspect-square bg-surface-muted flex items-center justify-center">
              {/* Using <img> here is intentional — poster URLs are dynamic from the backend */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.image_url} alt="Poster" className="w-full h-full object-contain" />
            </div>
            <div className="p-3 text-xs text-slate-500">
              Variation {p.variation_index + 1} · {p.provider}
            </div>
          </div>
        ))}
      </div>
      {eval_ && (
        <div className="glass rounded-xl p-6 border border-surface-border">
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

function AdCopyTab({ copies, campaignId, onGenerate, loading }: {
  copies: AdCopy[]; campaignId: string; onGenerate: () => void; loading: boolean;
}) {
  const [selected, setSelected] = useState(0);
  const copy = copies[selected];
  const PLATFORM_COLORS: Record<string, string> = {
    instagram: "text-pink-400", facebook: "text-blue-400",
    linkedin: "text-cyan-400", twitter: "text-sky-400", email: "text-amber-400",
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button onClick={onGenerate} disabled={loading}
          className="btn-brand px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
          Generate All Platforms
        </button>
      </div>
      {copies.length === 0 ? (
        <div className="glass rounded-xl p-10 border border-surface-border text-center text-slate-500 text-sm">
          No ad copies yet. Click Generate to create platform-specific copy.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          <div className="space-y-1">
            {copies.map((c, i) => (
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
            <div className="lg:col-span-3 glass rounded-xl p-5 border border-surface-border space-y-4">
              {copy.headline && (
                <p className="text-base font-semibold text-white">{copy.headline}</p>
              )}
              <p className="text-sm text-slate-300 whitespace-pre-wrap">{copy.body}</p>
              {copy.cta_variants?.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {copy.cta_variants.map((cta, i) => (
                    <span key={i} className="px-3 py-1 rounded-full text-xs bg-brand-500/20 text-brand-300 border border-brand-500/30">
                      {cta}
                    </span>
                  ))}
                </div>
              )}
              {copy.hashtags?.length > 0 && (
                <p className="text-xs text-slate-500">{copy.hashtags.map(h => `#${h}`).join(" ")}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PostingTab({ posts, campaignId, copies, posters, onPost, loading }: {
  posts: SocialPost[]; campaignId: string; copies: AdCopy[]; posters: Poster[];
  onPost: (platform: string, ad_copy_id?: string, poster_id?: string) => void;
  loading: boolean;
}) {
  const [platform, setPlatform] = useState("instagram");
  const icons: Record<string, string> = {
    posted: "✅", posting: "⏳", scheduled: "📅", failed: "❌", pending: "🔄",
  };

  return (
    <div className="space-y-6">
      <div className="glass rounded-xl p-5 border border-surface-border flex items-end gap-4">
        <div className="flex-1">
          <label className="text-xs text-slate-400 uppercase tracking-wide">Platform</label>
          <select className="input-dark mt-1" value={platform} onChange={e => setPlatform(e.target.value)}>
            {["instagram","facebook","linkedin","twitter"].map(p => (
              <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
            ))}
          </select>
        </div>
        <button onClick={() => onPost(platform, copies[0]?.id, posters[0]?.id)}
          disabled={loading}
          className="btn-brand px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 flex-shrink-0">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          Post Now
        </button>
      </div>
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-400">Post History</h3>
        {posts.length === 0 ? (
          <div className="glass rounded-xl p-8 border border-surface-border text-center text-slate-500 text-sm">
            No posts yet
          </div>
        ) : posts.map(p => (
          <div key={p.id} className="glass rounded-xl p-4 border border-surface-border flex items-center justify-between">
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
          Click &quot;Run LSTM Forecast&quot; to generate engagement predictions. Demo data will be seeded automatically.
        </div>
      ) : (
        <div className="glass rounded-xl p-6 border border-surface-border">
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
          <div className="glass rounded-xl p-6 border border-surface-border space-y-4">
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
          <div className="glass rounded-xl p-6 border border-surface-border space-y-3">
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
