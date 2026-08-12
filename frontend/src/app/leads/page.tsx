"use client";

import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { Loader2, Target, MessageSquare, Zap, Activity, Users, ShieldAlert } from "lucide-react";
import { api, Campaign, LeadScore, SentimentBatchResponse } from "@/lib/api";
import dynamic from "next/dynamic";

export default function LeadsAndSentimentPage() {
  const [tab, setTab] = useState<"leads" | "sentiment">("leads");
  
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center">
            <Target size={20} className="text-brand-400" />
          </div>
          Intelligence Hub
        </h1>
        <p className="text-slate-400 mt-2 text-sm">
          Lead Scoring (XGBoost) and Customer Sentiment Analysis (DistilBERT)
        </p>
      </div>

      <div className="flex gap-2 border-b border-surface-border pb-2">
        <button
          onClick={() => setTab("leads")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === "leads"
              ? "bg-brand-500/10 text-brand-300 border border-brand-500/20"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          XGBoost Lead Scoring
        </button>
        <button
          onClick={() => setTab("sentiment")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === "sentiment"
              ? "bg-brand-500/10 text-brand-300 border border-brand-500/20"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          DistilBERT Sentiment Analysis
        </button>
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
    lead_identifier: "user_" + Math.floor(Math.random() * 10000),
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
      setForm(f => ({ ...f, campaign_id: campaigns[0].id }));
    }
  }, [campaigns, form.campaign_id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.campaign_id) {
      toast.error("Please select a campaign");
      return;
    }

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

  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <div className="glass rounded-2xl p-6 border border-surface-border">
        <h2 className="text-lg font-semibold text-white mb-4">Input Lead Metrics</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="lead-campaign" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Campaign</label>
            <select id="lead-campaign" name="lead-campaign" className="input-dark" value={form.campaign_id} onChange={e => set("campaign_id", e.target.value)}>
              {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label htmlFor="lead-clicks" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Clicks</label>
              <input id="lead-clicks" name="lead-clicks" type="number" min={0} className="input-dark" value={form.clicks} onChange={e => set("clicks", Number(e.target.value))} />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="lead-views" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Views</label>
              <input id="lead-views" name="lead-views" type="number" min={0} className="input-dark" value={form.views} onChange={e => set("views", Number(e.target.value))} />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="lead-time" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Time Spent (sec)</label>
              <input id="lead-time" name="lead-time" type="number" min={0} className="input-dark" value={form.time_spent_seconds} onChange={e => set("time_spent_seconds", Number(e.target.value))} />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="lead-purchases" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Prior Purchases</label>
              <input id="lead-purchases" name="lead-purchases" type="number" min={0} className="input-dark" value={form.prior_purchases} onChange={e => set("prior_purchases", Number(e.target.value))} />
            </div>
            
            <div className="space-y-1.5">
              <label htmlFor="lead-source" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Source</label>
              <select id="lead-source" name="lead-source" className="input-dark" value={form.source_platform} onChange={e => set("source_platform", e.target.value)}>
                {["instagram", "facebook", "linkedin", "twitter", "email", "direct"].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="lead-device" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Device</label>
              <select id="lead-device" name="lead-device" className="input-dark" value={form.device} onChange={e => set("device", e.target.value)}>
                {["mobile", "desktop", "tablet"].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="lead-age" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Age Group</label>
              <select id="lead-age" name="lead-age" className="input-dark" value={form.age_group} onChange={e => set("age_group", e.target.value)}>
                {["18-24", "25-34", "35-44", "45-54", "55+"].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="lead-location" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Location Tier</label>
              <select id="lead-location" name="lead-location" className="input-dark" value={form.location_tier} onChange={e => set("location_tier", Number(e.target.value))}>
                {[1, 2, 3].map(p => <option key={p} value={p}>Tier {p}</option>)}
              </select>
            </div>
          </div>

          <button type="submit" disabled={loading || !form.campaign_id} className="btn-brand w-full py-2.5 rounded-xl font-medium flex justify-center items-center gap-2 mt-4">
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Activity size={16} />}
            Predict Lead Score
          </button>
        </form>
      </div>

      <div className="glass rounded-2xl p-6 border border-surface-border">
        <h2 className="text-lg font-semibold text-white mb-4">XGBoost Prediction</h2>
        {!result ? (
          <div className="h-48 flex items-center justify-center text-slate-500 text-sm border border-dashed border-surface-border rounded-xl">
            Submit metrics to view AI prediction
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex items-center gap-6">
              <div className="text-center">
                <div className={`text-4xl font-bold ${
                  result.category === 'hot' ? 'text-rose-400' :
                  result.category === 'warm' ? 'text-amber-400' : 'text-blue-400'
                }`}>
                  {Math.round(result.score)}
                </div>
                <div className="text-xs text-slate-400 mt-1 uppercase tracking-wider">Lead Score</div>
              </div>
              <div className="flex-1">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-white capitalize">{result.category} Lead</span>
                  <span className="text-sm text-brand-300">{(result.purchase_probability * 100).toFixed(1)}% Conversion</span>
                </div>
                <div className="h-3 bg-surface-muted rounded-full overflow-hidden">
                  <div 
                    className={`h-full rounded-full transition-all duration-1000 ${
                      result.category === 'hot' ? 'bg-rose-500' :
                      result.category === 'warm' ? 'bg-amber-500' : 'bg-blue-500'
                    }`}
                    style={{ width: `${result.purchase_probability * 100}%` }}
                  />
                </div>
              </div>
            </div>

            {result.feature_importance && (
              <div className="pt-4 border-t border-surface-border">
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Feature Importance</h3>
                <div className="space-y-2">
                  {Object.entries(result.feature_importance)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 5)
                    .map(([feature, imp]) => (
                      <div key={feature}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-300 capitalize">{feature.replace(/_/g, " ")}</span>
                          <span className="text-slate-500">{(imp * 100).toFixed(1)}%</span>
                        </div>
                        <div className="h-1.5 bg-surface-muted rounded-full overflow-hidden">
                          <div className="h-full bg-brand-500 rounded-full" style={{ width: `${imp * 100}%` }} />
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
  const [texts, setTexts] = useState<string>("I absolutely love this product, it's amazing!\nThe service was terrible, never buying again.\nIt's okay, does the job well enough.");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SentimentBatchResponse | null>(null);

  const handleAnalyze = async () => {
    const inputTexts = texts.split('\n').map(t => t.trim()).filter(Boolean);
    if (!inputTexts.length) {
      toast.error("Please enter at least one sentence");
      return;
    }

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
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <div className="glass rounded-2xl p-6 border border-surface-border">
        <h2 className="text-lg font-semibold text-white mb-4">Analyze Customer Feedback</h2>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="sentiment-texts" className="text-xs font-medium text-slate-400 uppercase tracking-wide">Feedback Texts (One per line)</label>
            <textarea
              id="sentiment-texts"
              name="sentiment-texts"
              className="input-dark h-48 resize-none font-mono text-sm leading-relaxed"
              value={texts}
              onChange={e => setTexts(e.target.value)}
              placeholder="Enter feedback comments here..."
            />
          </div>
          <button onClick={handleAnalyze} disabled={loading} className="btn-brand w-full py-2.5 rounded-xl font-medium flex justify-center items-center gap-2">
            {loading ? <Loader2 size={16} className="animate-spin" /> : <MessageSquare size={16} />}
            Analyze with DistilBERT
          </button>
        </div>
      </div>

      <div className="glass rounded-2xl p-6 border border-surface-border">
        <h2 className="text-lg font-semibold text-white mb-4">Sentiment Results</h2>
        {!result ? (
          <div className="h-48 flex items-center justify-center text-slate-500 text-sm border border-dashed border-surface-border rounded-xl">
            Run analysis to see model output
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-emerald-400">{result.summary.positive}</div>
                <div className="text-xs text-emerald-500/70 uppercase mt-0.5">Positive</div>
              </div>
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-amber-400">{result.summary.neutral}</div>
                <div className="text-xs text-amber-500/70 uppercase mt-0.5">Neutral</div>
              </div>
              <div className="bg-rose-500/10 border border-rose-500/20 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-rose-400">{result.summary.negative}</div>
                <div className="text-xs text-rose-500/70 uppercase mt-0.5">Negative</div>
              </div>
            </div>

            <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
              {result.results.map((r, i) => (
                <div key={i} className="p-3 bg-surface-muted/30 border border-surface-border rounded-lg space-y-2">
                  <p className="text-sm text-slate-300">"{r.text}"</p>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      r.label === 'positive' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                      r.label === 'negative' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' :
                      'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                    }`}>
                      {r.label} ({(r.confidence * 100).toFixed(1)}%)
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">
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