"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Campaign } from "@/lib/api";
import { Loader2, Megaphone, Plus, ExternalLink } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

const STATUS_BADGE: Record<string, string> = {
  draft:      "badge-pending",
  generating: "badge-pending",
  ready:      "badge-mock",
  posted:     "badge-posted",
  failed:     "badge-failed",
  archived:   "text-slate-600 bg-slate-800 border border-slate-700",
};

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.campaigns.list().then(setCampaigns).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Campaigns</h1>
          <p className="text-slate-400 text-sm mt-1">Manage all your marketing campaigns</p>
        </div>
        <Link href="/campaign/new"
          className="btn-brand px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2">
          <Plus size={16} /> New Campaign
        </Link>
      </div>

      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <Loader2 size={24} className="animate-spin text-brand-400" />
        </div>
      ) : campaigns.length === 0 ? (
        <div className="glass rounded-2xl p-16 border border-surface-border text-center">
          <Megaphone size={40} className="text-brand-400 mx-auto mb-4" />
          <p className="text-slate-300 font-semibold">No campaigns yet</p>
          <p className="text-slate-500 text-sm mt-2">Create your first AI-powered campaign</p>
          <Link href="/campaign/new"
            className="btn-brand inline-flex mt-5 px-5 py-2.5 rounded-xl text-sm font-semibold items-center gap-2">
            <Plus size={16} /> Launch Campaign
          </Link>
        </div>
      ) : (
        <div className="grid gap-4">
          {campaigns.map((c) => (
            <div key={c.id}
              className="glass rounded-xl border border-surface-border p-5 hover:border-brand-500/40 
                         transition-all duration-200 hover:shadow-card-hover group">
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="font-semibold text-white truncate">{c.name}</h3>
                    <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${STATUS_BADGE[c.status] || "badge-pending"}`}>
                      {c.status}
                    </span>
                  </div>
                  <p className="text-sm text-slate-400 truncate">{c.product_name}</p>
                  <div className="flex items-center gap-4 mt-2">
                    <span className="text-xs text-slate-500">{c.preferred_platform}</span>
                    <span className="text-xs text-slate-500">·</span>
                    <span className="text-xs text-slate-500">{c.campaign_goal.replace(/_/g, " ")}</span>
                    <span className="text-xs text-slate-500">·</span>
                    <span className="text-xs text-slate-600">
                      {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                    </span>
                  </div>
                </div>
                <Link href={`/campaign/${c.id}`}
                  className="flex items-center gap-1.5 text-xs text-brand-400 hover:text-brand-300 
                             opacity-0 group-hover:opacity-100 transition-opacity ml-4">
                  View <ExternalLink size={12} />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
