"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, TrendingUp, BarChart3, PieChart, Activity } from "lucide-react";
import { api, Campaign, Forecast } from "@/lib/api";
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

export default function AnalyticsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<string>("");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.campaigns.list().then(res => {
      setCampaigns(res);
      if (res.length > 0) setSelectedCampaign(res[0].id);
    });
  }, []);

  const runForecast = async () => {
    if (!selectedCampaign) return;
    setLoading(true);
    try {
      const f = await api.forecast.create(selectedCampaign, 14); // 14-day horizon
      setForecast(f);
      toast.success("Forecast generated!");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to generate forecast");
    } finally {
      setLoading(false);
    }
  };

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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="glass rounded-2xl p-6 border border-surface-border flex flex-col h-full">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-white">Global Engagement</h2>
            <p className="text-xs text-slate-500 mt-1">Platform-wide CTR and engagement metrics</p>
          </div>
          <div className="flex-1 mt-auto">
            <EngagementChart />
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
                value={selectedCampaign}
                onChange={e => setSelectedCampaign(e.target.value)}
              >
                {campaigns.length === 0 ? <option value="">No campaigns available</option> : null}
                {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <button 
                onClick={runForecast} 
                disabled={loading || !selectedCampaign}
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
    </div>
  );
}