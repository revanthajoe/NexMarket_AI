"use client";

import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, TrendingUp, BarChart3, Activity, RefreshCw, AlertTriangle } from "lucide-react";
import { api, invalidateCache, Campaign, Forecast, PlatformBreakdown, TrackingStatus } from "@/lib/api";
import dynamic from "next/dynamic";
import { DashboardStats } from "@/components/dashboard/DashboardStats";
import { ProvenanceBadge } from "@/components/ui/ProvenanceBadge";

const ForecastLineChart = dynamic(
  () => import("@/components/charts/ForecastLineChart").then((m) => m.ForecastLineChart),
  { ssr: false, loading: () => <div className="h-[280px] shimmer rounded-xl" /> }
);

const EngagementChart = dynamic(
  () => import("@/components/charts/EngagementChart").then((m) => m.EngagementChart),
  { ssr: false, loading: () => <div className="h-[240px] shimmer rounded-xl" /> }
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
  const [forecastState, setForecastState] = useState<string | null>(null);
  const [forecastActualCount, setForecastActualCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [platforms, setPlatforms] = useState<PlatformBreakdown[] | null>(null);
  const [tracking, setTracking] = useState<TrackingStatus | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api.campaigns.list().then((res) => {
      setCampaigns(res);
      if (res.length > 0) setForecastCampaign(res[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!forecastCampaign) {
      setForecastActualCount(0);
      return;
    }
    let cancelled = false;
    setForecastActualCount(0);
    api.analytics.trackingStatus(forecastCampaign).then((status) => {
      if (cancelled) return;
      const count = status.actual_event_count || 0;
      setForecastActualCount(count);
      setForecastState(count < 14 ? `Insufficient ACTUAL history — ${count}/14 observations.` : null);
    }).catch(() => {
      if (!cancelled) {
        setForecastActualCount(0);
        setForecastState("Unable to check ACTUAL history.");
      }
    });
    return () => { cancelled = true; };
  }, [forecastCampaign, refreshKey]);

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
    setForecastState(null);
    try {
      const f = await api.forecast.create(forecastCampaign, 14);
      setForecast(f);
      toast.success("Forecast generated!");
    } catch (err: unknown) {
      setForecast(null);
      const message = err instanceof Error ? err.message : "";
      setForecastState(message.includes("Insufficient ACTUAL history")
        ? "Insufficient ACTUAL history — 14 observations required."
        : "UNAVAILABLE: LSTM forecast model is unavailable");
      toast.error(message || "Failed to generate forecast");
    } finally {
      setLoading(false);
    }
  };

  const syncEngagement = async () => {
    const targets = selectedCampaign ? [selectedCampaign] : campaigns.map((c) => c.id);
    if (targets.length === 0) return;
    setSyncing(true);
    try {
      const results = await Promise.all(targets.map((id) => api.posting.syncMetrics(id)));
      const synced = results.reduce((n, r) => n + r.synced, 0);
      const checked = results.reduce((n, r) => n + r.posts_checked, 0);
      if (checked === 0) toast("No published posts to pull metrics from yet");
      else toast.success(`Synced ${synced}/${checked} posts`);
      invalidateCache();
      setRefreshKey((k) => k + 1);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Engagement sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const scopeName = selectedCampaign
    ? campaigns.find((c) => c.id === selectedCampaign)?.name ?? "campaign"
    : "all campaigns";

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
            <BarChart3 size={18} className="text-blue-600" />
          </div>
          Central Analytics Hub
        </h1>
        <p className="text-slate-500 mt-1.5 text-sm">
          Platform-wide performance and LSTM engagement forecasting
        </p>
      </div>

      {/* Stats */}
      <DashboardStats />

      {/* Tracking controls */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 flex flex-wrap items-end gap-4">
        <div className="flex-1 min-w-[220px]">
          <label htmlFor="analytics-scope" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            Scope
          </label>
          <select
            id="analytics-scope"
            name="analytics-scope"
            className="input-dark mt-2"
            value={selectedCampaign}
            onChange={(e) => setSelectedCampaign(e.target.value)}
          >
            <option value={ALL_CAMPAIGNS}>All campaigns</option>
            {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        <div>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Date range</span>
          <div className="flex gap-1 mt-2">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setDays(r)}
                className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                  days === r
                    ? "bg-blue-600 text-white shadow-brand"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
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
          className="btn-brand px-5 py-2.5 rounded-xl font-semibold flex items-center gap-2 disabled:opacity-50"
        >
          {syncing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          Sync Engagement
        </button>
      </div>

      {/* Provenance status row */}
      {tracking && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500 px-1">
          <span className="text-slate-600">
            <strong className="text-slate-800">{tracking.event_count}</strong> event{tracking.event_count === 1 ? "" : "s"} · {scopeName}
          </span>
          <span>{tracking.published_posts} published post{tracking.published_posts === 1 ? "" : "s"}</span>
          <span>Last synced {formatWhen(tracking.last_synced_at)}</span>
          {tracking.has_real_data ? (
            <span className="text-emerald-600 font-medium bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
              ● ACTUAL data available
            </span>
          ) : (
            <span className="text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
              No ACTUAL data yet
            </span>
          )}
          {tracking.mock_event_count > 0 && (
            <span className="flex items-center gap-1.5 text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
              <AlertTriangle size={11} />
              {tracking.mock_event_count} mock event{tracking.mock_event_count === 1 ? "" : "s"} — not real platform data
            </span>
          )}
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Engagement over time */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 flex flex-col">
          <div className="mb-4">
            <h2 className="text-base font-semibold text-slate-800">Engagement Over Time</h2>
            <p className="text-xs text-slate-500 mt-0.5">Daily likes and reach · last {days} days · {scopeName}</p>
          </div>
          <div className="flex-1">
            <EngagementChart days={days} campaignId={selectedCampaign || undefined} refreshKey={refreshKey} />
          </div>
        </div>

        {/* LSTM Forecast */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold text-slate-800">LSTM Campaign Forecast</h2>
              <p className="text-xs text-slate-500 mt-0.5">Predictive engagement modelling</p>
            </div>
            <Activity size={20} className="text-blue-400 opacity-60" />
          </div>

          <div className="flex gap-3 mb-5">
            <select
              id="forecast-campaign"
              name="forecast-campaign"
              className="input-dark flex-1 text-sm"
              value={forecastCampaign}
              onChange={(e) => setForecastCampaign(e.target.value)}
            >
              {campaigns.length === 0 ? <option value="">No campaigns available</option> : null}
              {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <button
              onClick={runForecast}
              disabled={loading || !forecastCampaign || forecastActualCount < 14}
              title={forecastActualCount < 14 ? "Forecasting requires 14 actual observations" : "Run forecast"}
              className="btn-brand px-4 py-2 rounded-xl font-semibold flex items-center gap-2 whitespace-nowrap"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <TrendingUp size={14} />}
              Run Forecast
            </button>
          </div>

          {forecast ? (
            <div className="space-y-3">
              <ForecastLineChart forecast={forecast} />
              <div className="flex justify-between items-center text-xs text-slate-400 pt-2 border-t border-slate-100">
                <span className="font-mono">
                  {forecast.model_version} · <ProvenanceBadge value={forecast.source_type} /> · history: {forecast.history_source || "UNKNOWN"}
                </span>
                <span className="bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
                  {forecast.forecast_horizon_days}d horizon
                </span>
              </div>
            </div>
          ) : (
            <div className="h-[240px] flex flex-col items-center justify-center text-slate-400 text-sm
                            border-2 border-dashed border-slate-200 rounded-xl">
              <TrendingUp size={24} className="text-slate-300 mb-2" />
              <p>{forecastState || "WAITING: select a campaign and run forecast"}</p>
              <p className="text-xs text-slate-300 mt-1">Requires ≥14 ACTUAL observations</p>
            </div>
          )}
        </div>
      </div>

      {/* Platform breakdown table */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6">
        <h2 className="text-base font-semibold text-slate-800 mb-1">Performance by Platform</h2>
        <p className="text-xs text-slate-500 mb-5">
          Totals over the last {days} days · CTR computed from summed clicks and impressions
        </p>

        {!platforms ? (
          <div className="h-[140px] shimmer rounded-xl" />
        ) : platforms.length === 0 ? (
          <div className="py-12 border-2 border-dashed border-slate-200 rounded-xl text-center text-sm text-slate-400">
            <BarChart3 size={24} className="text-slate-300 mx-auto mb-3" />
            <p>No engagement recorded yet.</p>
            <p className="text-xs mt-1 text-slate-300">Publish a post, then hit &quot;Sync Engagement&quot; to pull metrics.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-slate-400 border-b border-slate-200">
                  <th className="text-left font-semibold py-2.5 pr-4">Platform</th>
                  <th className="text-right font-semibold py-2.5 px-3">Impressions</th>
                  <th className="text-right font-semibold py-2.5 px-3">Reach</th>
                  <th className="text-right font-semibold py-2.5 px-3">Clicks</th>
                  <th className="text-right font-semibold py-2.5 px-3">CTR</th>
                  <th className="text-right font-semibold py-2.5 px-3">Engagement</th>
                  <th className="text-right font-semibold py-2.5 pl-3">Synced</th>
                </tr>
              </thead>
              <tbody>
                {platforms.map((p) => (
                  <tr key={p.platform} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                    <td className="py-3 pr-4 text-slate-700 capitalize font-medium flex items-center gap-2">
                      {p.platform}
                      {p.is_mock && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-50 text-blue-600 border border-blue-200 font-semibold">
                          Mock
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-right text-slate-600">{p.impressions.toLocaleString()}</td>
                    <td className="py-3 px-3 text-right text-slate-600">{p.reach.toLocaleString()}</td>
                    <td className="py-3 px-3 text-right text-slate-600">{p.clicks.toLocaleString()}</td>
                    <td className="py-3 px-3 text-right text-blue-600 font-medium">{(p.ctr * 100).toFixed(2)}%</td>
                    <td className="py-3 px-3 text-right text-slate-600">{(p.engagement_rate * 100).toFixed(2)}%</td>
                    <td className="py-3 pl-3 text-right text-slate-400 text-xs">{formatWhen(p.last_synced_at)}</td>
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
