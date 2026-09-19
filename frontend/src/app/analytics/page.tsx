"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, TrendingUp, BarChart3, Activity, RefreshCw, AlertTriangle } from "lucide-react";
import { api, invalidateCache, Campaign, Forecast, PlatformBreakdown, TrackingStatus } from "@/lib/api";
import dynamic from "next/dynamic";
import { DashboardStats } from "@/components/dashboard/DashboardStats";

const ForecastLineChart = dynamic(
  () => import("@/components/charts/ForecastLineChart").then((m) => m.ForecastLineChart),
  { ssr: false, loading: () => <div className="h-[280px] shimmer rounded-xl" /> }
);

const EngagementChart = dynamic(
  () => import("@/components/charts/EngagementChart").then((m) => m.EngagementChart),
  { ssr: false, loading: () => <div className="h-[220px] shimmer rounded-xl" /> }
);

const RANGES = [7, 14, 30, 90];
const ALL_CAMPAIGNS = "";

function formatWhen(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return d.toLocaleDateString();
}

export default function AnalyticsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<string>(ALL_CAMPAIGNS);
  const [forecastCampaign, setForecastCampaign] = useState<string>("");
  const [days, setDays] = useState(14);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [platforms, setPlatforms] = useState<PlatformBreakdown[] | null>(null);
  const [tracking, setTracking] = useState<TrackingStatus | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api.campaigns.list().then(res => {
      setCampaigns(res);
      if (res.length > 0) setForecastCampaign(res[0].id);
    }).catch(() => {});
  }, []);

  const loadTracking = useCallback(() => {
    const scope = selectedCampaign || undefined;
    setPlatforms(null);
    api.analytics.platforms(days, scope).then(setPlatforms).catch(() => setPlatforms([]));
    api.analytics.trackingStatus(scope).then(setTracking).catch(() => setTracking(null));
  }, [selectedCampaign, days]);

  useEffect(loadTracking, [loadTracking, refreshKey]);

  const runForecast = async () => {
    if (!forecastCampaign) return;
    setLoading(true);
    try {
      const f = await api.forecast.create(forecastCampaign, 14); // 14-day horizon
      setForecast(f);
      toast.success("Forecast generated!");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to generate forecast");
    } finally {
      setLoading(false);
    }
  };

  const syncEngagement = async () => {
    // Syncing is per-campaign on the backend; with "All campaigns" selected we
    // fan out rather than silently syncing nothing.
    const targets = selectedCampaign ? [selectedCampaign] : campaigns.map(c => c.id);
    if (targets.length === 0) return;
    setSyncing(true);
    try {
      const results = await Promise.all(targets.map(id => api.posting.syncMetrics(id)));
      const synced = results.reduce((n, r) => n + r.synced, 0);
      const checked = results.reduce((n, r) => n + r.posts_checked, 0);
      if (checked === 0) toast("No published posts to pull metrics from yet");
      else toast.success(`Synced ${synced}/${checked} posts`);
      invalidateCache();
      setRefreshKey(k => k + 1);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Engagement sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const scopeName = selectedCampaign
    ? campaigns.find(c => c.id === selectedCampaign)?.name ?? "campaign"
    : "all campaigns";

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center">
            <BarChart3 size={20} className="text-brand-400" />
          </div>
          Central Analytics Hub
        </h1>
        <p className="text-slate-400 mt-2 text-sm">
          Platform-wide performance and LSTM engagement forecasting
        </p>
      </div>

      <DashboardStats />

      {/* ── Tracking controls ─────────────────────────────────────────── */}
      <div className="glass rounded-2xl p-5 border border-surface-border flex flex-wrap items-end gap-4">
        <div className="flex-1 min-w-[220px]">
          <label htmlFor="analytics-scope" className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            Scope
          </label>
          <select
            id="analytics-scope"
            className="input-dark mt-2"
            value={selectedCampaign}
            onChange={e => setSelectedCampaign(e.target.value)}
          >
            <option value={ALL_CAMPAIGNS}>All campaigns</option>
            {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        <div>
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Range</span>
          <div className="flex gap-1 mt-2">
            {RANGES.map(r => (
              <button
                key={r}
                onClick={() => setDays(r)}
                className={`px-3 py-2 rounded-lg text-xs transition-colors ${
                  days === r
                    ? "bg-brand-500/20 text-brand-300 border border-brand-500/40"
                    : "bg-surface-muted text-slate-400 border border-surface-border hover:text-slate-200"
                }`}
              >
                {r}d
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={syncEngagement}
          disabled={syncing || campaigns.length === 0}
          className="btn-brand px-5 py-2.5 rounded-xl font-medium flex items-center gap-2 disabled:opacity-50"
        >
          {syncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          Sync Engagement
        </button>
      </div>

      {/* ── Provenance ────────────────────────────────────────────────── */}
      {tracking && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500 px-1">
          <span>
            {tracking.event_count} event{tracking.event_count === 1 ? "" : "s"} · {scopeName}
          </span>
          <span>{tracking.published_posts} published post{tracking.published_posts === 1 ? "" : "s"}</span>
          <span>Last synced {formatWhen(tracking.last_synced_at)}</span>
          {tracking.mock_event_count > 0 && (
            <span className="flex items-center gap-1.5 text-amber-400">
              <AlertTriangle size={12} />
              {tracking.mock_event_count} of these came from the mock adapter — not real platform data
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="glass rounded-2xl p-6 border border-surface-border flex flex-col h-full">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-white">Engagement Over Time</h2>
            <p className="text-xs text-slate-500 mt-1">Daily likes and reach · last {days} days · {scopeName}</p>
          </div>
          <div className="flex-1 mt-auto">
            <EngagementChart days={days} campaignId={selectedCampaign || undefined} refreshKey={refreshKey} />
          </div>
        </div>

        <div className="glass rounded-2xl p-6 border border-surface-border">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">LSTM Campaign Forecast</h2>
              <p className="text-xs text-slate-500 mt-1">Predictive engagement modelling</p>
            </div>
            <Activity size={24} className="text-brand-400 opacity-50" />
          </div>

          <div className="space-y-4 mb-6">
            <div className="flex gap-4">
              <select
                className="input-dark flex-1"
                value={forecastCampaign}
                onChange={e => setForecastCampaign(e.target.value)}
              >
                {campaigns.length === 0 ? <option value="">No campaigns available</option> : null}
                {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <button
                onClick={runForecast}
                disabled={loading || !forecastCampaign}
                className="btn-brand px-5 py-2.5 rounded-xl font-medium flex items-center gap-2"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <TrendingUp size={16} />}
                Run Forecast
              </button>
            </div>
          </div>

          {forecast ? (
            <div className="space-y-4">
              <ForecastLineChart forecast={forecast} />
              <div className="flex justify-between items-center text-xs text-slate-500 pt-2 border-t border-surface-border">
                <span>Model: {forecast.model_version}</span>
                <span>Horizon: {forecast.forecast_horizon_days} Days</span>
              </div>
            </div>
          ) : (
            <div className="h-[280px] flex items-center justify-center text-slate-500 text-sm border border-dashed border-surface-border rounded-xl bg-surface-muted/10">
              Select a campaign and run forecast to view predictions
            </div>
          )}
        </div>
      </div>

      {/* ── Platform breakdown ────────────────────────────────────────── */}
      <div className="glass rounded-2xl p-6 border border-surface-border">
        <h2 className="text-lg font-semibold text-white mb-1">Performance by Platform</h2>
        <p className="text-xs text-slate-500 mb-5">
          Totals over the last {days} days · CTR computed from summed clicks and impressions
        </p>

        {!platforms ? (
          <div className="h-[140px] shimmer rounded-xl" />
        ) : platforms.length === 0 ? (
          <div className="p-10 border border-dashed border-surface-border rounded-xl text-center text-sm text-slate-500">
            No engagement recorded yet. Publish a post, then hit Sync Engagement to pull metrics back
            from the platform.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-slate-500 border-b border-surface-border">
                  <th className="text-left font-medium py-2 pr-4">Platform</th>
                  <th className="text-right font-medium py-2 px-3">Impressions</th>
                  <th className="text-right font-medium py-2 px-3">Reach</th>
                  <th className="text-right font-medium py-2 px-3">Clicks</th>
                  <th className="text-right font-medium py-2 px-3">CTR</th>
                  <th className="text-right font-medium py-2 px-3">Engagement</th>
                  <th className="text-right font-medium py-2 pl-3">Synced</th>
                </tr>
              </thead>
              <tbody>
                {platforms.map(p => (
                  <tr key={p.platform} className="border-b border-surface-border/50 last:border-0">
                    <td className="py-3 pr-4 text-slate-200 capitalize flex items-center gap-2">
                      {p.platform}
                      {p.is_mock && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] badge-mock">Mock</span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-right text-slate-300">{p.impressions.toLocaleString()}</td>
                    <td className="py-3 px-3 text-right text-slate-300">{p.reach.toLocaleString()}</td>
                    <td className="py-3 px-3 text-right text-slate-300">{p.clicks.toLocaleString()}</td>
                    <td className="py-3 px-3 text-right text-brand-300">{(p.ctr * 100).toFixed(2)}%</td>
                    <td className="py-3 px-3 text-right text-slate-300">{(p.engagement_rate * 100).toFixed(2)}%</td>
                    <td className="py-3 pl-3 text-right text-slate-500 text-xs">{formatWhen(p.last_synced_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
