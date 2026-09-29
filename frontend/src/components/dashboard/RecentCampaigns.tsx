"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Campaign, api } from "@/lib/api";

const STATUS_BADGE: Record<string, string> = {
  draft:      "bg-slate-100 text-slate-600 border border-slate-200",
  generating: "bg-blue-100 text-blue-700 border border-blue-200",
  ready:      "bg-cyan-100 text-cyan-700 border border-cyan-200",
  posted:     "bg-emerald-100 text-emerald-700 border border-emerald-200",
  failed:     "bg-rose-100 text-rose-700 border border-rose-200",
};

export function RecentCampaigns() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.campaigns.list()
      .then(res => setCampaigns(res.slice(0, 5)))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-14 shimmer rounded-xl" />
        ))}
      </div>
    );
  }

  if (campaigns.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">No campaigns found.</p>
    );
  }

  return (
    <div className="space-y-2">
      {campaigns.map(c => (
        <Link key={c.id} href={`/campaign/${c.id}`} className="block group">
          <div className="bg-white border border-slate-200 rounded-xl p-3 flex items-center justify-between hover:border-blue-300 hover:shadow-sm transition-all">
            <div>
              <p className="text-sm font-semibold text-slate-800 group-hover:text-blue-700">{c.name}</p>
              <p className="text-xs text-slate-500 mt-0.5">{c.product_name} · {c.preferred_platform}</p>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[c.status] || STATUS_BADGE.draft}`}>
              {c.status}
            </span>
          </div>
        </Link>
      ))}
    </div>
  );
}
