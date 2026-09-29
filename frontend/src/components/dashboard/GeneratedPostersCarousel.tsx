"use client";

import { useEffect, useState } from "react";
import { api, Poster } from "@/lib/api";
import { ImageIcon } from "lucide-react";
import { getPosterImageUrl, isMockPoster } from "@/lib/poster";

export function GeneratedPostersCarousel() {
  const [posters, setPosters] = useState<Poster[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadPosters() {
      try {
        const campaigns = await api.campaigns.list();
        const recentCampaigns = campaigns.slice(0, 3); // Check top 3 campaigns for posters
        const posterPromises = recentCampaigns.map(c => api.posters.getByCampaign(c.id));
        const posterResults = await Promise.all(posterPromises);
        const allPosters = posterResults.flat();
        setPosters(allPosters.filter((poster) => !isMockPoster(poster.provider)).slice(0, 10)); // Take top 10
      } catch (err) {
        console.error("Failed to load posters", err);
      } finally {
        setLoading(false);
      }
    }
    loadPosters();
  }, []);

  if (loading) {
    return (
      <div className="flex gap-4 h-[240px] overflow-hidden">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex-1 bg-slate-100 rounded-xl overflow-hidden shimmer border border-slate-200" />
        ))}
      </div>
    );
  }

  if (posters.length === 0) {
    return (
      <div className="flex gap-4 h-[240px] overflow-hidden">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex-1 bg-slate-100 rounded-xl overflow-hidden relative group border border-slate-200">
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-3 z-10">
              <span className="text-white text-xs font-medium truncate">No Posters</span>
            </div>
            <div className="w-full h-full flex flex-col items-center justify-center text-slate-400 gap-2 bg-slate-50 group-hover:scale-105 transition-transform duration-500">
               <ImageIcon size={32} className="opacity-50" />
               <span className="text-[10px] font-mono tracking-widest uppercase">Mock</span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-4 h-[240px] overflow-x-auto snap-x snap-mandatory pb-2">
      {posters.map((p) => {
        const resolvedSrc = getPosterImageUrl(p.image_url);
        return (
          <div key={p.id} className="min-w-[160px] max-w-[160px] flex-1 bg-slate-100 rounded-xl overflow-hidden relative group border border-slate-200 snap-center flex-shrink-0">
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-3 z-10">
              <span className="text-white text-xs font-medium truncate">{p.prompt_used || "AI Poster"}</span>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img 
              src={resolvedSrc} 
              alt="Generated Poster" 
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
              onError={(e) => {
                const target = e.target as HTMLImageElement;
                target.src = "data:image/svg+xml;charset=UTF-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400' fill='none'%3E%3Crect width='400' height='400' fill='%23f1f5f9'/%3E%3Cpath d='M200 160c-22.1 0-40 17.9-40 40s17.9 40 40 40 40-17.9 40-40-17.9-40-40-40zm0 64c-13.2 0-24-10.8-24-24s10.8-24 24-24 24 10.8 24 24-10.8 24-24 24z' fill='%2394a3b8'/%3E%3C/svg%3E";
              }}
            />
          </div>
        );
      })}
    </div>
  );
}
