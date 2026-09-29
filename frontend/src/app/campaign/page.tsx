"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, Campaign } from "@/lib/api";
import { Loader2, Megaphone, Plus, ChevronRight, Clock } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

const STATUS_BADGE: Record<string, string> = {
  draft:      "bg-slate-100 text-slate-600 border border-slate-200",
  generating: "bg-blue-100 text-blue-700 border border-blue-200",
  ready:      "bg-cyan-100 text-cyan-700 border border-cyan-200",
  posted:     "bg-emerald-100 text-emerald-700 border border-emerald-200",
  failed:     "bg-rose-100 text-rose-700 border border-rose-200",
  archived:   "bg-slate-100 text-slate-500 border border-slate-200",
};

const STATUS_DOT: Record<string, string> = {
  draft:      "bg-slate-400",
  generating: "bg-blue-500 animate-pulse",
  ready:      "bg-cyan-500",
  posted:     "bg-emerald-500",
  failed:     "bg-rose-500",
  archived:   "bg-slate-300",
};

const PAGE_SIZE = 20;

function CampaignSkeleton() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="flex items-center justify-between">
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-3">
            <div className="w-36 h-4 rounded shimmer" />
            <div className="w-16 h-5 rounded-full shimmer" />
          </div>
          <div className="w-48 h-3.5 rounded shimmer" />
          <div className="w-64 h-3 rounded shimmer" />
        </div>
        <div className="w-6 h-6 rounded shimmer ml-4" />
      </div>
    </div>
  );
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [page, setPage] = useState(0);

  useEffect(() => {
    api.campaigns.list()
      .then(setCampaigns)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const pageCount = Math.max(1, Math.ceil(campaigns.length / PAGE_SIZE));
  const visible = useMemo(
    () => campaigns.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [campaigns, page],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Campaigns</h1>
          <p className="text-slate-500 text-sm mt-1">Manage all your marketing campaigns</p>
        </div>
        <Link
          href="/campaign/new"
          className="btn-brand px-4 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"
        >
          <Plus size={16} />
          New Campaign
        </Link>
      </div>

      {/* Content */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => <CampaignSkeleton key={i} />)}
        </div>
      ) : error ? (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-center">
          <p className="text-rose-700 font-medium text-sm">Failed to load campaigns</p>
          <p className="text-rose-500 text-xs mt-1">Check that the backend is running</p>
        </div>
      ) : campaigns.length === 0 ? (
        <div className="bg-white border-2 border-dashed border-slate-200 rounded-2xl p-16 text-center">
          <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center mx-auto mb-4">
            <Megaphone size={24} className="text-blue-500" />
          </div>
          <p className="text-slate-800 font-semibold text-base">No campaigns yet</p>
          <p className="text-slate-500 text-sm mt-1">Create your first AI-powered campaign to get started</p>
          <Link
            href="/campaign/new"
            className="btn-brand inline-flex mt-5 px-5 py-2.5 rounded-xl text-sm font-semibold items-center gap-2"
          >
            <Plus size={16} />
            Launch Campaign
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {visible.map((c, i) => (
            <Link
              key={c.id}
              href={`/campaign/${c.id}`}
              className="block bg-white border border-slate-200 rounded-xl p-5
                         hover:border-blue-300 hover:shadow-card-hover transition-all duration-150 group animate-fade-in-up"
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <div className="flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Name + status */}
                  <div className="flex items-center gap-3 mb-1.5">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[c.status] || "bg-slate-400"}`} />
                    <h3 className="font-semibold text-slate-900 truncate group-hover:text-blue-700 transition-colors">
                      {c.name}
                    </h3>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full flex-shrink-0 font-medium ${STATUS_BADGE[c.status] || STATUS_BADGE.draft}`}>
                      {c.status}
                    </span>
                  </div>

                  {/* Product name */}
                  <p className="text-sm text-slate-600 truncate">{c.product_name}</p>

                  {/* Meta row */}
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <span className="text-xs text-slate-400 bg-slate-50 border border-slate-200 rounded px-2 py-0.5 capitalize">
                      {c.preferred_platform}
                    </span>
                    <span className="text-xs text-slate-400 bg-slate-50 border border-slate-200 rounded px-2 py-0.5">
                      {c.campaign_goal.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <Clock size={10} />
                      {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                    </span>
                  </div>
                </div>

                <ChevronRight
                  size={16}
                  className="text-slate-300 group-hover:text-blue-500 flex-shrink-0 transition-colors"
                />
              </div>
            </Link>
          ))}

          {/* Pagination */}
          {pageCount > 1 && (
            <div className="flex items-center justify-center gap-4 pt-4">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-4 py-2 rounded-lg text-sm border border-slate-200 text-slate-600
                           hover:bg-slate-50 hover:border-slate-300 disabled:opacity-40 transition-colors"
              >
                Previous
              </button>
              <span className="text-sm text-slate-500">
                Page {page + 1} of {pageCount} · {campaigns.length} campaigns
              </span>
              <button
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                disabled={page >= pageCount - 1}
                className="px-4 py-2 rounded-lg text-sm border border-slate-200 text-slate-600
                           hover:bg-slate-50 hover:border-slate-300 disabled:opacity-40 transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
