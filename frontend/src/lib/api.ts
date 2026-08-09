/**
 * NexMarket AI — API Client
 * Thin wrapper around fetch/axios for all backend calls.
 */

let activeBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const FALLBACK_PORTS = [8000, 8001, 8002, 8003, 8004, 8005];

async function req<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  let res: Response | null = null;
  let fetchError: unknown = null;

  // Fault tolerance: Automatically scan common ports if local backend shifts
  if (activeBase.match(/(localhost|127\.0\.0\.1):\d+/)) {
    const currentPortMatch = activeBase.match(/(?:localhost|127\.0\.0\.1):(\d+)/);
    const currentPort = currentPortMatch ? parseInt(currentPortMatch[1]) : 8000;
    
    // Always try the known active port first, then fallbacks
    const portsToTry = [...new Set([currentPort, ...FALLBACK_PORTS])];

    for (const port of portsToTry) {
      const testBase = activeBase.replace(/(localhost|127\.0\.0\.1):\d+/, `$1:${port}`);
      try {
        res = await fetch(`${testBase}${path}`, {
          headers: { "Content-Type": "application/json", ...options.headers },
          ...options,
        });
        
        // Request connected! Update activeBase so future requests are fast
        activeBase = testBase;
        fetchError = null;
        break;
      } catch (err: unknown) {
        fetchError = err; // Connection refused, try next port
      }
    }
  } else {
    try {
      res = await fetch(`${activeBase}${path}`, {
        headers: { "Content-Type": "application/json", ...options.headers },
        ...options,
      });
    } catch (err: unknown) {
      fetchError = err;
    }
  }

  if (fetchError || !res) {
    throw new Error("Failed to connect to the backend. Please ensure uvicorn is running.");
  }

  if (!res.ok) {
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await res.json();
      const detail = data?.detail;
      if (Array.isArray(detail)) {
        const message = detail
          .map((item: { loc?: Array<string | number>; msg?: string }) => {
            const field = item.loc?.slice(1).join(".") || "request";
            return `${field}: ${item.msg || "invalid value"}`;
          })
          .join("; ");
        throw new Error(message || `HTTP ${res.status}`);
      }
      if (typeof detail === "string") {
        throw new Error(detail);
      }
      throw new Error(JSON.stringify(data) || `HTTP ${res.status}`);
    }
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Campaigns ────────────────────────────────────────────────────────────────
export const api = {
  campaigns: {
    list: ()                  => req<Campaign[]>("/campaigns/"),
    get:  (id: string)        => req<Campaign>(`/campaigns/${id}`),
    create: (data: CampaignCreate) =>
      req<Campaign>("/campaigns/", { method: "POST", body: JSON.stringify(data) }),
    updateStatus: (id: string, status: string) =>
      req(`/campaigns/${id}/status?status_val=${status}`, { method: "PATCH" }),
    delete: (id: string) =>
      req(`/campaigns/${id}`, { method: "DELETE" }),
  },

  posters: {
    generate: (campaign_id: string, variations = 1) =>
      req<Poster[]>("/posters/generate", {
        method: "POST",
        body: JSON.stringify({ campaign_id, variations }),
      }),
    evaluate: (poster_id: string) =>
      req<PosterEvaluation>(`/posters/${poster_id}/evaluate`, { method: "POST" }),
  },

  adcopy: {
    generate: (campaign_id: string, platforms: string[], tone = "professional") =>
      req<AdCopy[]>("/adcopy/generate", {
        method: "POST",
        body: JSON.stringify({ campaign_id, platforms, tone }),
      }),
    getByCampaign: (campaign_id: string) =>
      req<AdCopy[]>(`/adcopy/${campaign_id}`),
  },

  posting: {
    publish: (data: PostRequest) =>
      req<SocialPost>("/posting/publish", { method: "POST", body: JSON.stringify(data) }),
    getBycampaign: (campaign_id: string) =>
      req<SocialPost[]>(`/posting/campaign/${campaign_id}`),
    getStatus: (post_id: string) =>
      req<SocialPost>(`/posting/${post_id}`),
    retry: (post_id: string) =>
      req<SocialPost>(`/posting/retry/${post_id}`, { method: "POST" }),
    healthCheck: () => req<Record<string, boolean>>("/posting/health/platforms"),
  },

  sentiment: {
    analyze: (texts: string[], campaign_id?: string) =>
      req<SentimentBatchResponse>("/sentiment/analyze", {
        method: "POST",
        body: JSON.stringify({ texts, campaign_id }),
      }),
  },

  leads: {
    predict: (data: LeadScoreRequest) =>
      req<LeadScore>("/leads/predict", { method: "POST", body: JSON.stringify(data) }),
    getByCampaign: (campaign_id: string) =>
      req(`/leads/campaign/${campaign_id}`),
  },

  forecast: {
    create: (campaign_id: string, horizon_days = 7) =>
      req<Forecast>("/forecast/", {
        method: "POST",
        body: JSON.stringify({ campaign_id, horizon_days }),
      }),
    getByCampaign: (campaign_id: string) =>
      req(`/forecast/campaign/${campaign_id}`),
  },

  optimize: {
    run: (campaign_id: string, budget?: number) =>
      req<Optimization>("/optimize/", {
        method: "POST",
        body: JSON.stringify({ campaign_id, budget }),
      }),
  },

  analytics: {
    dashboard: () => req<DashboardSummary>("/analytics/dashboard"),
    getCampaign: (campaign_id: string) =>
      req<AnalyticsEvent[]>(`/analytics/campaign/${campaign_id}`),
    seedDemo: (campaign_id: string) =>
      req(`/analytics/campaign/${campaign_id}/seed-demo`, { method: "POST" }),
  },

  n8n: {
    trigger: (campaign_id: string, steps?: string[]) =>
      req<N8nResponse>("/n8n/trigger/campaign", {
        method: "POST",
        body: JSON.stringify({ campaign_id, steps }),
      }),
    status: (campaign_id: string) =>
      req(`/n8n/status/${campaign_id}`),
  },
};

// ── Types ─────────────────────────────────────────────────────────────────────
export interface Campaign {
  id: string;
  name: string;
  product_name: string;
  description: string;
  offer: string;
  target_audience: string;
  campaign_goal: string;
  preferred_platform: string;
  brand_style?: string;
  budget?: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CampaignCreate {
  name: string;
  product_name: string;
  description: string;
  offer: string;
  target_audience: string;
  campaign_goal: string;
  preferred_platform: string;
  brand_style?: string;
  budget?: number;
  post_schedule?: string;
}

export interface Poster {
  id: string;
  campaign_id: string;
  image_url: string;
  prompt_used?: string;
  provider: string;
  variation_index: number;
  created_at: string;
}

export interface PosterEvaluation {
  id: string;
  poster_id: string;
  overall_score: number;
  readability_score: number;
  layout_score: number;
  branding_score: number;
  contrast_score: number;
  cta_score: number;
  visual_appeal_score: number;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  created_at: string;
}

export interface AdCopy {
  id: string;
  campaign_id: string;
  platform: string;
  headline?: string;
  body: string;
  cta_variants: string[];
  hashtags: string[];
  tone?: string;
  created_at: string;
}

export interface SocialPost {
  id: string;
  campaign_id: string;
  platform: string;
  status: string;
  platform_post_id?: string;
  platform_url?: string;
  scheduled_at?: string;
  posted_at?: string;
  retry_count: number;
  error_message?: string;
  is_mock: boolean;
  created_at: string;
}

export interface PostRequest {
  campaign_id: string;
  platform: string;
  ad_copy_id?: string;
  poster_id?: string;
  scheduled_at?: string;
}

export interface SentimentBatchResponse {
  results: SentimentResult[];
  summary: { positive: number; negative: number; neutral: number };
}

export interface SentimentResult {
  text: string;
  label: string;
  positive_score: number;
  negative_score: number;
  neutral_score: number;
  confidence: number;
  model_used: string;
}

export interface LeadScoreRequest {
  campaign_id: string;
  lead_identifier: string;
  clicks: number;
  views: number;
  time_spent_seconds: number;
  source_platform: string;
  prior_purchases: number;
  device: string;
  age_group: string;
  location_tier: number;
}

export interface LeadScore {
  score: number;
  purchase_probability: number;
  category: string;
  feature_importance?: Record<string, number>;
}

export interface Forecast {
  campaign_id: string;
  forecast_horizon_days: number;
  predicted_likes: number[];
  predicted_shares: number[];
  predicted_comments: number[];
  predicted_ctr: number[];
  predicted_reach: number[];
  confidence_intervals?: Record<string, { lower: number[]; upper: number[] }>;
  model_version: string;
  created_at: string;
}

export interface Optimization {
  recommended_platform: string;
  recommended_time?: string;
  recommended_budget?: number;
  confidence: number;
  reasoning?: string;
  platform_scores?: Record<string, number>;
  created_at: string;
}

export interface DashboardSummary {
  total_campaigns: number;
  active_campaigns: number;
  total_posts: number;
  successful_posts: number;
  avg_engagement_rate: number;
  total_leads: number;
  hot_leads: number;
}

export interface AnalyticsEvent {
  date: string;
  platform: string;
  impressions: number;
  clicks: number;
  likes: number;
  shares: number;
  comments: number;
  reach: number;
  ctr: number;
  spend: number;
}

export interface N8nResponse {
  status: string;
  message: string;
  data?: Record<string, unknown>;
}
