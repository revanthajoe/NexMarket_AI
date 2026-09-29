"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Send, Activity, RefreshCw, BarChart3, AlertTriangle } from "lucide-react";
import { api, Campaign, IntegrationStatus, SocialPost } from "@/lib/api";

export default function PostingStudioPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<string>("");
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [health, setHealth] = useState<Record<string, IntegrationStatus> | null>(null);

  useEffect(() => {
    api.campaigns.list().then((res) => {
      setCampaigns(res);
      if (res.length > 0) setSelectedCampaign(res[0].id);
    }).catch(() => {});

    api.posting.integrationsStatus().then(setHealth).catch(() => {});
  }, []);

  const handleSyncMetrics = async () => {
    if (!selectedCampaign) return;
    setSyncing(true);
    try {
      const r = await api.posting.syncMetrics(selectedCampaign);
      if (r.posts_checked === 0) {
        toast("No published posts to sync yet");
      } else {
        toast.success(
          `Synced ${r.synced}/${r.posts_checked} posts` +
          (r.failed ? ` · ${r.failed} failed` : "") +
          (r.mock_sourced ? ` · ${r.mock_sourced} from mock adapter` : "")
        );
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Metrics sync failed");
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    if (!selectedCampaign) return;
    setLoading(true);
    api.posting.getBycampaign(selectedCampaign)
      .then(setPosts)
      .catch(() => toast.error("Failed to load posts"))
      .finally(() => setLoading(false));
  }, [selectedCampaign]);

  const handleRetry = async (postId: string) => {
    try {
      await api.posting.retry(postId);
      toast.success("Post retry initiated");
      const updated = await api.posting.getBycampaign(selectedCampaign);
      setPosts(updated);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to retry post");
    }
  };

  const icons: Record<string, string> = {
    posted: "✅", pending: "⏳", failed: "❌",
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
            <Send size={18} className="text-blue-600" />
          </div>
          Social Media Posting Studio
        </h1>
        <p className="text-slate-500 mt-1.5 text-sm">
          Monitor and manage cross-platform social media distributions
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 animate-fade-in-up">
            <label htmlFor="posting-campaign" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Select Campaign
            </label>
            <select
              id="posting-campaign"
              name="posting-campaign"
              className="input-dark mt-2"
              value={selectedCampaign}
              onChange={(e) => setSelectedCampaign(e.target.value)}
            >
              {campaigns.length === 0 && <option value="">No campaigns available</option>}
              {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl p-6 animate-fade-in-up delay-100">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-4">
              <h2 className="text-base font-semibold text-slate-800">Post Timeline</h2>
              <button
                onClick={handleSyncMetrics}
                disabled={syncing || !selectedCampaign}
                className="text-xs px-4 py-2 rounded-lg bg-slate-50 border border-slate-200 hover:bg-slate-100 hover:border-slate-300 transition-colors text-slate-600 font-medium flex items-center gap-2 disabled:opacity-50"
              >
                {syncing ? <Loader2 size={13} className="animate-spin text-blue-500" /> : <BarChart3 size={13} className="text-slate-400" />}
                Sync Engagement Metrics
              </button>
            </div>
            {loading ? (
              <div className="flex justify-center p-12"><Loader2 className="animate-spin text-blue-500" /></div>
            ) : posts.length === 0 ? (
              <div className="p-12 border-2 border-dashed border-slate-200 rounded-xl flex flex-col items-center justify-center text-slate-500 text-sm gap-3">
                <Send size={24} className="text-slate-300" />
                No posts found for this campaign.
              </div>
            ) : (
              <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
                {posts.map((p, i) => (
                  <div key={p.id} className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex items-start sm:items-center justify-between gap-4 animate-fade-in-up" style={{ animationDelay: `${i * 80}ms` }}>
                    <div className="flex items-start sm:items-center gap-3">
                      <span className="text-xl leading-none mt-0.5 sm:mt-0">{icons[p.status] || "🔄"}</span>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-slate-800 capitalize">{p.platform}</p>
                          {p.is_mock && <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-50 text-blue-600 border border-blue-200 font-semibold">Mock</span>}
                        </div>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {new Date(p.created_at).toLocaleString()}
                        </p>
                        {p.error_message && (
                          <div className="flex gap-1.5 mt-2 bg-rose-50 text-rose-700 px-3 py-2 rounded-lg text-xs border border-rose-100">
                            <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
                            <span className="leading-relaxed">{p.error_message}</span>
                          </div>
                        )}
                      </div>
                    </div>
                    {p.status === "failed" && (
                      <button onClick={() => handleRetry(p.id)} className="p-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 hover:border-slate-300 transition-colors text-slate-500 flex-shrink-0 shadow-sm">
                        <RefreshCw size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4 animate-fade-in-up delay-150">
          <div className="bg-white border border-slate-200 rounded-2xl p-6">
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-5 flex items-center gap-2">
              <Activity size={15} /> API Health Status
            </h2>
            {!health ? (
              <div className="flex justify-center p-8"><Loader2 className="animate-spin text-slate-400" /></div>
            ) : (
              <div className="space-y-2.5">
                {Object.entries(health).map(([platform, s]) => {
                  const label = !s.configured
                    ? { text: "Not configured", dot: "bg-slate-400", fg: "text-slate-500", border: "border-slate-200", bg: "bg-slate-50" }
                    : s.healthy
                      ? { text: "Operational", dot: "bg-emerald-500", fg: "text-emerald-700", border: "border-emerald-200", bg: "bg-emerald-50" }
                      : { text: "Credentials failing", dot: "bg-rose-500", fg: "text-rose-700", border: "border-rose-200", bg: "bg-rose-50" };
                  return (
                    <div key={platform} className={`flex justify-between items-center p-3.5 rounded-xl border ${label.border} ${label.bg}`}>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-700 capitalize">{platform}</span>
                        {s.mode === "mock" && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-100 text-blue-700 border border-blue-200 font-semibold">Mock</span>
                        )}
                      </div>
                      <span className="flex items-center gap-1.5 text-xs font-medium">
                        <span className={`w-2 h-2 rounded-full ${label.dot}`} />
                        <span className={label.fg}>{label.text}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            <p className="text-[10px] text-slate-400 leading-relaxed mt-4 pt-4 border-t border-slate-100">
              Note: Mock adapters always report as healthy since they bypass real external API credential checks.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}