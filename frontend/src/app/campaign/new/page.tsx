"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { Loader2, Megaphone, ChevronRight } from "lucide-react";
import { api, CampaignCreate } from "@/lib/api";

const PLATFORMS = ["instagram", "facebook", "linkedin", "twitter", "all"];
const GOALS = [
  "brand_awareness", "lead_generation", "sales_conversion",
  "engagement", "app_downloads", "website_traffic",
];

export default function NewCampaignPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [autoRun, setAutoRun] = useState(true);

  const [form, setForm] = useState<CampaignCreate & { post_now: boolean }>({
    name: "",
    product_name: "",
    description: "",
    offer: "",
    target_audience: "",
    campaign_goal: "brand_awareness",
    preferred_platform: "instagram",
    brand_style: "",
    budget: undefined,
    post_now: true,
  });

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { post_now, ...payload } = form;
      const campaign = await api.campaigns.create(payload);
      toast.success(`Campaign "${campaign.name}" created!`);

      if (autoRun) {
        await api.n8n.trigger(campaign.id, [
          "poster", "adcopy", "evaluate", "forecast", "optimize", "post",
        ]);
        toast.success("🚀 AI pipeline started — poster, copy, and post queued!");
      }

      router.push(`/campaign/${campaign.id}`);
    } catch (err: unknown) {
      toast.error("Failed to create campaign");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm text-slate-500 mb-4">
          <span>Dashboard</span><ChevronRight size={14} /><span className="text-slate-300">New Campaign</span>
        </div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center">
            <Megaphone size={20} className="text-brand-400" />
          </div>
          Launch New Campaign
        </h1>
        <p className="text-slate-400 text-sm mt-2">
          Fill in product details — AI handles poster generation, ad copy, and social posting automatically.
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <Section title="Campaign Info">
          <Field label="Campaign Name" required>
            <input
              className="input-dark"
              placeholder="Summer Sale 2024"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              required
            />
          </Field>
          <Field label="Product / Service Name" required>
            <input
              className="input-dark"
              placeholder="CloudNotes Pro"
              value={form.product_name}
              onChange={(e) => set("product_name", e.target.value)}
              required
            />
          </Field>
          <Field label="Product Description" required>
            <textarea
              className="input-dark h-24 resize-none"
              placeholder="Describe your product — what it does and why people love it"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              required
            />
          </Field>
        </Section>

        <Section title="Offer & Audience">
          <Field label="Offer / Promotion" required>
            <input
              className="input-dark"
              placeholder="50% off annual subscription"
              value={form.offer}
              onChange={(e) => set("offer", e.target.value)}
              required
            />
          </Field>
          <Field label="Target Audience" required>
            <input
              className="input-dark"
              placeholder="Remote workers and college students aged 22-35"
              value={form.target_audience}
              onChange={(e) => set("target_audience", e.target.value)}
              required
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Campaign Goal" required>
              <select
                className="input-dark"
                value={form.campaign_goal}
                onChange={(e) => set("campaign_goal", e.target.value)}
              >
                {GOALS.map((g) => (
                  <option key={g} value={g}>
                    {g.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Preferred Platform" required>
              <select
                className="input-dark"
                value={form.preferred_platform}
                onChange={(e) => set("preferred_platform", e.target.value)}
              >
                {PLATFORMS.map((p) => (
                  <option key={p} value={p}>
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </Section>

        <Section title="Budget & Style (Optional)">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Budget (USD)">
              <input
                type="number"
                className="input-dark"
                placeholder="500"
                min={0}
                value={form.budget ?? ""}
                onChange={(e) => set("budget", e.target.value ? Number(e.target.value) : undefined)}
              />
            </Field>
            <Field label="Brand Style">
              <input
                className="input-dark"
                placeholder="minimalist, dark, luxury…"
                value={form.brand_style ?? ""}
                onChange={(e) => set("brand_style", e.target.value)}
              />
            </Field>
          </div>
        </Section>

        {/* Auto-run toggle */}
        <div className="glass rounded-xl p-4 border border-surface-border flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-white">🤖 Auto-run full AI pipeline</p>
            <p className="text-xs text-slate-500 mt-0.5">
              Generate poster, ad copy, forecast, optimize and post automatically
            </p>
          </div>
          <button
            type="button"
            onClick={() => setAutoRun(!autoRun)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              autoRun ? "bg-brand-500" : "bg-surface-border"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                autoRun ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="btn-brand w-full py-3 rounded-xl font-semibold text-base flex items-center justify-center gap-2"
        >
          {loading ? (
            <><Loader2 size={18} className="animate-spin" /> Launching…</>
          ) : (
            <><Megaphone size={18} /> Launch Campaign</>
          )}
        </button>
      </form>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass rounded-2xl p-6 border border-surface-border space-y-4">
      <h2 className="text-sm font-semibold text-brand-400 uppercase tracking-wider">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, required, children }: {
  label: string; required?: boolean; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">
        {label}{required && <span className="text-brand-400 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}
