"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Target, MessageSquare, Activity, Users } from "lucide-react";
import { api, Campaign, LeadScore, SentimentBatchResponse } from "@/lib/api";

export default function LeadsAndSentimentPage() {
  const [tab, setTab] = useState<"leads" | "sentiment">("leads");

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-violet-50 flex items-center justify-center">
            <Users size={18} className="text-violet-600" />
          </div>
          Intelligence Hub
        </h1>
        <p className="text-slate-500 mt-1.5 text-sm">
          Lead Scoring (XGBoost) and Customer Sentiment Analysis (DistilBERT)
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <div className="flex gap-1">
          {(["leads", "sentiment"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                tab === t
                  ? "text-blue-700 border-blue-600 bg-blue-50/50"
                  : "text-slate-500 border-transparent hover:text-slate-800"
              }`}
            >
              {t === "leads" ? "XGBoost Lead Scoring" : "DistilBERT Sentiment Analysis"}
            </button>
          ))}
        </div>
      </div>

      {tab === "leads" ? <LeadScoringSection /> : <SentimentSection />}
    </div>
  );
}

function LeadScoringSection() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LeadScore | null>(null);

  const [form, setForm] = useState({
    campaign_id: "",
    lead_identifier: "manual-lead",
    clicks: 12,
    views: 45,
    time_spent_seconds: 120,
    source_platform: "instagram",
    prior_purchases: 0,
    device: "mobile",
    age_group: "25-34",
    location_tier: 1,
  });

  useEffect(() => {
    api.campaigns.list().then(setCampaigns).catch(() => {});
  }, []);

  useEffect(() => {
    if (campaigns.length > 0 && !form.campaign_id) {
      setForm((f) => ({ ...f, campaign_id: campaigns[0].id }));
    }
  }, [campaigns, form.campaign_id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.campaign_id) { toast.error("Please select a campaign"); return; }
    setLoading(true);
    try {
      const res = await api.leads.predict(form);
      setResult(res);
      toast.success("Lead scored successfully");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to score lead");
    } finally {
      setLoading(false);
    }
  };

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const CATEGORY_STYLES: Record<string, string> = {
    hot:  "text-rose-700 bg-rose-50 border-rose-200",
    warm: "text-amber-700 bg-amber-50 border-amber-200",
    cold: "text-blue-700 bg-blue-50 border-blue-200",
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white border border-slate-200 rounded-2xl p-6">
        <h2 className="text-base font-semibold text-slate-800 mb-4">Input Lead Metrics</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="lead-campaign" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Campaign</label>
            <select id="lead-campaign" name="lead-campaign" className="input-dark" value={form.campaign_id} onChange={(e) => set("campaign_id", e.target.value)}>
              {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[
              { id: "lead-clicks", key: "clicks", label: "Clicks", type: "number" },
              { id: "lead-views", key: "views", label: "Views", type: "number" },
              { id: "lead-time", key: "time_spent_seconds", label: "Time Spent (sec)", type: "number" },
              { id: "lead-purchases", key: "prior_purchases", label: "Prior Purchases", type: "number" },
            ].map(({ id, key, label, type }) => (
              <div key={key} className="space-y-1">
                <label htmlFor={id} className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</label>
                <input
                  id={id} name={id} type={type} min={0} className="input-dark text-sm"
                  value={form[key as keyof typeof form] as number}
                  onChange={(e) => set(key, Number(e.target.value))}
                />
              </div>
            ))}

            {[
              { id: "lead-source", key: "source_platform", label: "Source", opts: ["instagram", "facebook", "linkedin", "twitter", "email", "direct"] },
              { id: "lead-device", key: "device", label: "Device", opts: ["mobile", "desktop", "tablet"] },
              { id: "lead-age", key: "age_group", label: "Age Group", opts: ["18-24", "25-34", "35-44", "45-54", "55+"] },
            ].map(({ id, key, label, opts }) => (
              <div key={key} className="space-y-1">
                <label htmlFor={id} className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</label>
                <select id={id} name={id} className="input-dark text-sm" value={form[key as keyof typeof form] as string} onChange={(e) => set(key, e.target.value)}>
                  {opts.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
            ))}

            <div className="space-y-1">
              <label htmlFor="lead-location" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Location Tier</label>
              <select id="lead-location" name="lead-location" className="input-dark text-sm" value={form.location_tier} onChange={(e) => set("location_tier", Number(e.target.value))}>
                {[1, 2, 3].map((p) => <option key={p} value={p}>Tier {p}</option>)}
              </select>
            </div>
          </div>

          <button type="submit" disabled={loading || !form.campaign_id}
            className="btn-brand w-full py-2.5 rounded-xl font-semibold flex justify-center items-center gap-2 mt-2">
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Activity size={16} />}
            Predict Lead Score
          </button>
        </form>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-6">
        <h2 className="text-base font-semibold text-slate-800 mb-4">XGBoost Prediction</h2>
        {!result ? (
          <div className="h-48 flex flex-col items-center justify-center text-slate-400 text-sm border-2 border-dashed border-slate-200 rounded-xl gap-2">
            <Target size={24} className="text-slate-300" />
            Submit metrics to view AI prediction
          </div>
        ) : (
          <div className="space-y-5 animate-scale-up">
            <div className="text-xs uppercase tracking-wide text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full inline-block font-semibold">
              {result.source_type || "UNKNOWN"}{result.is_fallback ? " · FALLBACK" : ""}
            </div>

            <div className="flex items-center gap-6">
              <div className="text-center">
                <div className={`text-5xl font-bold ${
                  result.category === "hot" ? "text-rose-600" :
                  result.category === "warm" ? "text-amber-600" : "text-blue-600"
                }`}>
                  {Math.round(result.score)}
                </div>
                <div className="text-xs text-slate-400 mt-1 uppercase tracking-wider font-medium">Lead Score</div>
              </div>
              <div className="flex-1">
                <div className="flex justify-between items-center mb-2">
                  <span className={`text-sm font-semibold px-3 py-1 rounded-full border ${CATEGORY_STYLES[result.category] || CATEGORY_STYLES.cold} capitalize`}>
                    {result.category} Lead
                  </span>
                  <span className="text-sm font-semibold text-blue-600">
                    {(result.purchase_probability * 100).toFixed(1)}% probability
                  </span>
                </div>
                <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-1000 ${
                      result.category === "hot" ? "bg-rose-500" :
                      result.category === "warm" ? "bg-amber-500" : "bg-blue-500"
                    }`}
                    style={{ width: `${result.purchase_probability * 100}%` }}
                  />
                </div>
              </div>
            </div>

            {result.feature_importance && (
              <div className="pt-4 border-t border-slate-100">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Feature Importance</h3>
                <div className="space-y-2.5">
                  {Object.entries(result.feature_importance)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 5)
                    .map(([feature, imp]) => (
                      <div key={feature}>
                        <div className="flex justify-between text-sm mb-1.5">
                          <span className="text-slate-600 capitalize font-medium">{feature.replace(/_/g, " ")}</span>
                          <span className="text-slate-400 font-mono text-xs">{(imp * 100).toFixed(1)}%</span>
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-violet-500 to-blue-400 rounded-full" style={{ width: `${imp * 100}%` }} />
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SentimentSection() {
  const [texts, setTexts] = useState<string>(
    "I absolutely love this product, it's amazing!\nThe service was terrible, never buying again.\nIt's okay, does the job well enough."
  );
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SentimentBatchResponse | null>(null);

  const handleAnalyze = async () => {
    const inputTexts = texts.split("\n").map((t) => t.trim()).filter(Boolean);
    if (!inputTexts.length) { toast.error("Please enter at least one sentence"); return; }
    setLoading(true);
    try {
      const res = await api.sentiment.analyze(inputTexts);
      setResult(res);
      toast.success("Sentiment analyzed!");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to analyze sentiment");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white border border-slate-200 rounded-2xl p-6">
        <h2 className="text-base font-semibold text-slate-800 mb-4">Analyze Customer Feedback</h2>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="sentiment-texts" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Feedback Texts (one per line)
            </label>
            <textarea
              id="sentiment-texts"
              name="sentiment-texts"
              className="input-dark h-48 resize-none font-mono text-sm leading-relaxed"
              value={texts}
              onChange={(e) => setTexts(e.target.value)}
              placeholder="Enter feedback comments here..."
            />
          </div>
          <button onClick={handleAnalyze} disabled={loading}
            className="btn-brand w-full py-2.5 rounded-xl font-semibold flex justify-center items-center gap-2">
            {loading ? <Loader2 size={16} className="animate-spin" /> : <MessageSquare size={16} />}
            Analyze with DistilBERT
          </button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-6">
        <h2 className="text-base font-semibold text-slate-800 mb-4">Sentiment Results</h2>
        {!result ? (
          <div className="h-48 flex flex-col items-center justify-center text-slate-400 text-sm border-2 border-dashed border-slate-200 rounded-xl gap-2">
            <MessageSquare size={24} className="text-slate-300" />
            Run analysis to see model output
          </div>
        ) : (
          <div className="space-y-5 animate-scale-up">
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-center">
                <div className="text-2xl font-bold text-emerald-700">{result.summary.positive}</div>
                <div className="text-xs text-emerald-600 uppercase mt-0.5 font-medium">Positive</div>
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-center">
                <div className="text-2xl font-bold text-amber-700">{result.summary.neutral}</div>
                <div className="text-xs text-amber-600 uppercase mt-0.5 font-medium">Neutral</div>
              </div>
              <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-center">
                <div className="text-2xl font-bold text-rose-700">{result.summary.negative}</div>
                <div className="text-xs text-rose-600 uppercase mt-0.5 font-medium">Negative</div>
              </div>
            </div>

            <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
              {result.results.map((r, i) => (
                <div key={i} className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                  <p className="text-sm text-slate-700 italic">&quot;{r.text}&quot;</p>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${
                      r.label === "positive" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                      r.label === "negative" ? "bg-rose-50 text-rose-700 border-rose-200" :
                      "bg-amber-50 text-amber-700 border-amber-200"
                    }`}>
                      {r.label} ({(r.confidence * 100).toFixed(1)}%)
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono hidden sm:inline">
                      Pos: {r.positive_score.toFixed(2)} | Neg: {r.negative_score.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}