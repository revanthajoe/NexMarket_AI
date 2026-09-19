"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Send, Activity, RefreshCw, BarChart3 } from "lucide-react";
import { api, Campaign, IntegrationStatus, SocialPost } from "@/lib/api";

export default function PostingStudioPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<string>("");
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [health, setHealth] = useState<Record<string, IntegrationStatus> | null>(null);

  useEffect(() => {
    api.campaigns.list().then(res => {
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
    posted: "✅", pending: "⏳", failed: "❌"
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center">
            <Send size={20} className="text-brand-400" />
          </div>
          Social Media Posting Studio
        </h1>
        <p className="text-slate-400 mt-2 text-sm">
          Monitor and manage cross-platform social media distributions
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-4">
          <div className="glass-dynamic rounded-xl p-5 animate-fade-in-up">
            <label htmlFor="posting-campaign" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Select Campaign</label>
            <select 
              id="posting-campaign"
              name="posting-campaign"
              className="input-dark mt-2" 
              value={selectedCampaign} 
              onChange={e => setSelectedCampaign(e.target.value)}
            >
              {campaigns.length === 0 && <option value="">No campaigns available</option>}
              {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>

          <div className="glass-dynamic rounded-xl p-5 animate-fade-in-up delay-100">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Post Timeline</h2>
              <button
                onClick={handleSyncMetrics}
                disabled={syncing || !selectedCampaign}
                className="text-xs px-3 py-2 rounded-lg bg-surface-muted hover:bg-surface-border transition-colors text-slate-300 flex items-center gap-2 disabled:opacity-50"
              >
                {syncing ? <Loader2 size={13} className="animate-spin" /> : <BarChart3 size={13} />}
                Sync Engagement
              </button>
            </div>
            {loading ? (
              <div className="flex justify-center p-10"><Loader2 className="animate-spin text-brand-400" /></div>
            ) : posts.length === 0 ? (
              <div className="p-10 border border-dashed border-surface-border rounded-xl text-center text-slate-500 text-sm">
                No posts found for this campaign.
              </div>
            ) : (
              <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
                {posts.map((p, i) => (
                  <div key={p.id} className="glass-dynamic rounded-xl p-4 flex items-center justify-between animate-fade-in-up" style={{ animationDelay: `${i * 100}ms` }}>
                    <div className="flex items-center gap-3">
                      <span className="text-xl">{icons[p.status] || "🔄"}</span>
                      <div>
                        <p className="text-sm font-medium text-white capitalize">{p.platform}</p>
                        <p className="text-xs text-slate-500">
                          {new Date(p.created_at).toLocaleString()} {p.is_mock && <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] badge-mock">Mock</span>}
                        </p>
                        {p.error_message && <p className="text-xs text-rose-400 mt-1">{p.error_message}</p>}
                      </div>
                    </div>
                    {p.status === "failed" && (
                      <button onClick={() => handleRetry(p.id)} className="p-2 rounded-lg bg-surface-muted hover:bg-surface-border transition-colors text-slate-300">
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
          <div className="glass-dynamic rounded-xl p-6">
            <h2 className="text-sm font-semibold text-brand-400 uppercase tracking-wide mb-4 flex items-center gap-2">
              <Activity size={16} /> API Health Status
            </h2>
            {!health ? (
              <div className="flex justify-center p-4"><Loader2 className="animate-spin text-slate-500" /></div>
            ) : (
              <div className="space-y-3">
                {Object.entries(health).map(([platform, s]) => {
                  // A mock adapter always answers "healthy" — showing that as
                  // Operational claimed a connection that doesn't exist.
                  const label = !s.configured
                    ? { text: "Not configured", dot: "bg-slate-500", fg: "text-slate-400" }
                    : s.healthy
                      ? { text: "Operational", dot: "bg-emerald-400 animate-pulse", fg: "text-emerald-400" }
                      : { text: "Credentials failing", dot: "bg-rose-400", fg: "text-rose-400" };
                  return (
                    <div key={platform} className="flex justify-between items-center p-3 rounded-lg bg-surface-muted/30 border border-surface-border">
                      <span className="text-sm text-slate-300 capitalize flex items-center gap-2">
                        {platform}
                        {s.mode === "mock" && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] badge-mock">Mock</span>
                        )}
                      </span>
                      <span className="flex items-center gap-1.5 text-xs">
                        <span className={`w-2 h-2 rounded-full ${label.dot}`} />
                        <span className={label.fg}>{label.text}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}