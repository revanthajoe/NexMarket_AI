"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Megaphone } from "lucide-react";
import { AdCopy, Campaign, api } from "@/lib/api";
import { AdCopyTab } from "@/components/campaign/CampaignTabs";

export default function AdCopyPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [copies, setCopies] = useState<AdCopy[]>([]);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [loadingCopies, setLoadingCopies] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    api.campaigns.list().then((items) => {
      setCampaigns(items);
      if (items.length) setCampaignId(items[0].id);
    }).catch(() => toast.error("Failed to load campaigns"))
      .finally(() => setLoadingCampaigns(false));
  }, []);

  useEffect(() => {
    if (!campaignId) {
      setCopies([]);
      return;
    }
    let cancelled = false;
    setLoadingCopies(true);
    api.adcopy.getByCampaign(campaignId)
      .then((items) => { if (!cancelled) setCopies(items); })
      .catch(() => toast.error("Failed to load ad copy"))
      .finally(() => { if (!cancelled) setLoadingCopies(false); });
    return () => { cancelled = true; };
  }, [campaignId]);

  const generate = async (platforms: string[], tone: string, language: string) => {
    if (!campaignId) return;
    setGenerating(true);
    try {
      const generated = await api.adcopy.generate(campaignId, platforms, tone, language);
      setCopies((current) => [...current, ...generated]);
      toast.success("Ad copy generated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to generate ad copy");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight text-slate-900">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50">
            <Megaphone size={18} className="text-blue-600" />
          </span>
          Ad Copy Studio
        </h1>
        <p className="mt-1.5 text-sm text-slate-500">Create and manage campaign copy by platform.</p>
      </header>

      <section className="max-w-2xl space-y-2">
        <label htmlFor="adcopy-campaign" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Campaign
        </label>
        <select
          id="adcopy-campaign"
          name="adcopy-campaign"
          className="input-dark w-full"
          value={campaignId}
          onChange={(event) => setCampaignId(event.target.value)}
          disabled={!campaigns.length}
        >
          {campaigns.length === 0 && <option value="">No campaigns available</option>}
          {campaigns.map((campaign) => (
            <option key={campaign.id} value={campaign.id}>{campaign.name}</option>
          ))}
        </select>
      </section>

      {loadingCampaigns || (campaignId && loadingCopies) ? (
        <div className="flex min-h-48 items-center justify-center text-slate-500" role="status">
          <Loader2 size={18} className="animate-spin" />
        </div>
      ) : !campaignId ? (
        <div className="rounded-xl border-2 border-dashed border-slate-200 bg-white p-12 text-center text-sm text-slate-500">
          Create a campaign to generate ad copy.
        </div>
      ) : (
        <AdCopyTab
          copies={copies}
          campaignId={campaignId}
          onGenerate={generate}
          loading={generating}
        />
      )}
    </div>
  );
}