"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { Loader2, Megaphone, ChevronRight } from "lucide-react";
import { api, PIPELINE_STEPS, LANGUAGES, CampaignCreate } from "@/lib/api";

const PLATFORMS = ["instagram", "facebook", "telegram", "whatsapp", "all"];
const GOALS = [
  "brand_awareness", "lead_generation", "sales_conversion",
  "engagement", "app_downloads", "website_traffic",
];

const Field = ({ label, htmlFor, required, error, children }: {
  label: string, htmlFor?: string, required?: boolean, error?: string, children: React.ReactNode,
}) => (
  <div className="space-y-1.5">
    <label htmlFor={htmlFor} className="text-xs font-medium text-slate-400 uppercase tracking-wide">
      {label} {required && <span className="text-brand-400">*</span>}
    </label>
    {children}
    {error && <p className="text-xs text-red-400">{error}</p>}
  </div>
);

const Section = ({ title, children }: { title: string, children: React.ReactNode }) => (
  <div className="glass-dynamic rounded-2xl p-6 border border-surface-border animate-fade-in-up">
    <h2 className="text-lg font-semibold text-slate-800 mb-4">{title}</h2>
    <div className="space-y-4">
      {children}
    </div>
  </div>
);

export default function NewCampaignPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [autoRun, setAutoRun] = useState(true);
  const [language, setLanguage] = useState("en");
  const [errors, setErrors] = useState<Record<string, string>>({});

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

  const set = (k: string, v: unknown) => {
    setForm((f) => ({ ...f, [k]: v }));
    setErrors((e) => {
      if (!e[k]) return e;
      const next = { ...e };
      delete next[k];
      return next;
    });
  };

  const validateForm = (): Record<string, string> => {
    const errors: Record<string, string> = {};

    if (form.name.trim().length < 2) errors.name = "Campaign name must be at least 2 characters";
    if (form.product_name.trim().length < 2) errors.product_name = "Product / service name must be at least 2 characters";
    if (form.description.trim().length < 10) errors.description = "Description must be at least 10 characters";
    if (form.offer.trim().length < 5) errors.offer = "Offer / promotion must be at least 5 characters";
    if (form.target_audience.trim().length < 5) errors.target_audience = "Target audience must be at least 5 characters";
    if (!PLATFORMS.includes(form.preferred_platform)) errors.preferred_platform = "Select a valid platform";
    if (!GOALS.includes(form.campaign_goal)) errors.campaign_goal = "Select a valid campaign goal";
    if (form.budget !== undefined && form.budget < 0) errors.budget = "Budget cannot be negative";

    return errors;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const found = validateForm();
    setErrors(found);
    if (Object.keys(found).length > 0) {
      toast.error(`Please fix ${Object.keys(found).length} field${Object.keys(found).length > 1 ? "s" : ""} below`);
      return;
    }

    setLoading(true);
    let campaign: Awaited<ReturnType<typeof api.campaigns.create>> | null = null;
    try {
      const { post_now, ...payload } = form;
      const normalizedPayload = {
        ...payload,
        name: payload.name.trim(),
        product_name: payload.product_name.trim(),
        description: payload.description.trim(),
        offer: payload.offer.trim(),
        target_audience: payload.target_audience.trim(),
        brand_style: payload.brand_style?.trim() || undefined,
      };
      campaign = await api.campaigns.create(normalizedPayload);
      toast.success(`Campaign "${campaign.name}" created!`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to create campaign");
      setLoading(false);
      return;
    }

    if (campaign) {
      // Persist the language before the pipeline starts — the backend reads the
      // brand kit when generating, so setting it afterwards would be too late.
      try {
        await api.brandKit.setMeta(campaign.id, { language });
      } catch {
        toast.error("Campaign created, but the language setting could not be saved.");
      }

      if (autoRun) {
        try {
          await api.n8n.trigger(campaign.id, PIPELINE_STEPS);
          toast.success("🚀 AI pipeline started — follow progress on the campaign page.");
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : "Unknown pipeline error";
          toast.error(`Campaign created, but the pipeline could not be started: ${message}`);
        }
      }

      router.push(`/campaign/${campaign.id}`);
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
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-3">
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
          <Field label="Campaign Name" htmlFor="campaign-name" required error={errors.name}>
            <input
              id="campaign-name"
              name="campaign-name"
              className="input-dark"
              placeholder="Summer Sale 2024"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              required
            />
          </Field>
          <Field label="Product / Service Name" htmlFor="product-name" required error={errors.product_name}>
            <input
              id="product-name"
              name="product-name"
              className="input-dark"
              placeholder="CloudNotes Pro"
              value={form.product_name}
              onChange={(e) => set("product_name", e.target.value)}
              required
            />
          </Field>
          <Field label="Product Description" htmlFor="product-description" required error={errors.description}>
            <textarea
              id="product-description"
              name="product-description"
              className="input-dark h-24 resize-none"
              placeholder="Describe your product — what it does and why people love it"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              required
            />
          </Field>
        </Section>

        <Section title="Offer & Audience">
          <Field label="Offer / Promotion" htmlFor="offer" required error={errors.offer}>
            <input
              id="offer"
              name="offer"
              className="input-dark"
              placeholder="50% off annual subscription"
              value={form.offer}
              onChange={(e) => set("offer", e.target.value)}
              required
            />
          </Field>
          <Field label="Target Audience" htmlFor="target-audience" required error={errors.target_audience}>
            <input
              id="target-audience"
              name="target-audience"
              className="input-dark"
              placeholder="Remote workers and college students aged 22-35"
              value={form.target_audience}
              onChange={(e) => set("target_audience", e.target.value)}
              required
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Campaign Goal" htmlFor="campaign-goal" required error={errors.campaign_goal}>
              <select
                id="campaign-goal"
                name="campaign-goal"
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
            <Field label="Preferred Platform" htmlFor="preferred-platform" required error={errors.preferred_platform}>
              <select
                id="preferred-platform"
                name="preferred-platform"
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

        <Section title="Optional Settings">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Budget (USD)" htmlFor="budget" error={errors.budget}>
              <input
                id="budget"
                name="budget"
                type="number"
                className="input-dark"
                placeholder="500"
                min={0}
                value={form.budget ?? ""}
                onChange={(e) => set("budget", e.target.value ? Number(e.target.value) : undefined)}
              />
            </Field>
            <Field label="Visual Style Hint" htmlFor="brand-style">
              <input
                id="brand-style"
                name="brand-style"
                className="input-dark"
                placeholder="minimalist, dark, luxury…"
                value={form.brand_style ?? ""}
                onChange={(e) => set("brand_style", e.target.value)}
              />
              <p className="text-[11px] text-slate-600">
                Free-text mood for the AI art direction. Logo, fonts and brand colour
                are uploaded separately in the campaign&apos;s Brand Kit.
              </p>
            </Field>
          </div>
          <Field label="Poster &amp; Ad Copy Language" htmlFor="campaign-language">
            <select
              id="campaign-language"
              name="campaign-language"
              className="input-dark"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </Field>
        </Section>

        {/* Auto-run toggle */}
        <div className="glass rounded-xl p-4 border border-surface-border flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-800">Auto-run full AI pipeline</p>
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
