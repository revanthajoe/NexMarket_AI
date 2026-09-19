/**
 * NexMarket AI — API Client
 * Thin wrapper around fetch/axios for all backend calls.
 */

let activeBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const FALLBACK_PORTS = [8000, 8001, 8002, 8003, 8004, 8005];

const REQUEST_TIMEOUT_MS = 30_000;
// AI-heavy endpoints (SDXL poster generation, vision evaluation) need much longer
const AI_REQUEST_TIMEOUT_MS = 7_200_000; // 2 hours

/**
 * GET response cache. Every page fetches with a bare useEffect, so navigating
 * between pages refetched everything from scratch. Entries are short-lived and
 * the whole cache is dropped on any mutation, so a write is never masked by a
 * stale read. In-flight requests are shared, which also collapses the duplicate
 * fetches React strict mode fires on mount.
 */
const GET_CACHE_TTL_MS = 10_000;
const getCache = new Map<string, { at: number; promise: Promise<unknown> }>();

/** Drop all cached GETs. Called automatically on every mutation; call it
 *  manually when data changed server-side without a request from this client
 *  (e.g. after a background pipeline finishes). */
export function invalidateCache() {
  getCache.clear();
}

async function req<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();

  if (method === "GET") {
    const hit = getCache.get(path);
    if (hit && Date.now() - hit.at < GET_CACHE_TTL_MS) {
      return hit.promise as Promise<T>;
    }
    const promise = rawReq<T>(path, options, timeoutMs);
    getCache.set(path, { at: Date.now(), promise });
    // A failed request must not be served from cache on the next call.
    promise.catch(() => getCache.delete(path));
    return promise;
  }

  invalidateCache();
  return rawReq<T>(path, options, timeoutMs);
}

async function rawReq<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
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
      const isFormData = options.body && typeof (options.body as any).append === "function";
      
      // We must completely omit Content-Type for FormData so the browser sets the boundary
      const customHeaders: Record<string, string> = { ...(options.headers as Record<string, string>) };
      if (!isFormData) {
        customHeaders["Content-Type"] = "application/json";
      } else {
        delete customHeaders["Content-Type"];
      }

      const fetchOpts = {
        ...options,
        headers: customHeaders,
        signal: controller.signal,
      };

      try {
        res = await fetch(`${testBase}${path}`, fetchOpts);

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
      const isFormData = options.body && typeof (options.body as any).append === "function";
      
      const customHeaders: Record<string, string> = { ...(options.headers as Record<string, string>) };
      if (!isFormData) {
        customHeaders["Content-Type"] = "application/json";
      } else {
        delete customHeaders["Content-Type"];
      }

      const fetchOpts = {
        ...options,
        headers: customHeaders,
        signal: controller.signal,
      };

      res = await fetch(`${activeBase}${path}`, fetchOpts);
    } catch (err: unknown) {
      fetchError = err;
    }
  }

  clearTimeout(timeoutId);

  if (fetchError || !res) {
    const isTimeout = fetchError instanceof DOMException && fetchError.name === "AbortError";
    throw new Error(isTimeout
      ? "Request timed out. Please ensure the backend is running."
      : "Failed to connect to the backend. Please ensure uvicorn is running."
    );
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

/** The one definition of "run the full pipeline" — shared by the new-campaign
 *  auto-run and the campaign detail page's Run Pipeline button. */
export const PIPELINE_STEPS = [
  "poster", "adcopy", "evaluate", "forecast", "optimize", "post",
];

/** Campaign statuses that mean the pipeline is still working. */
export const PIPELINE_ACTIVE_STATUSES = ["generating"];

/** Ad copy tones the backend accepts. */
export const AD_COPY_TONES = [
  "professional", "casual", "playful", "urgent", "luxury", "inspirational",
];

/** Platform body-text limits, used to warn before publishing. */
export const PLATFORM_CHAR_LIMITS: Record<string, number> = {
  instagram: 2200,
  facebook: 63206,
  telegram: 4096,
  whatsapp: 4096,
  email: 100000,
};

/** Languages supported for poster CTA text and ad copy. Codes must match
 *  the backend's `_CTA_MAP` in app/services/ai/poster_generator.py. */
export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिन्दी (Hindi)" },
  { code: "ta", label: "தமிழ் (Tamil)" },
  { code: "te", label: "తెలుగు (Telugu)" },
  { code: "mr", label: "मराठी (Marathi)" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
];

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
    getByCampaign: (campaign_id: string) =>
      req<Poster[]>(`/posters/campaign/${campaign_id}`),
    generate: (campaign_id: string, variations = 1, language?: string) =>
      req<Poster[]>("/posters/generate", {
        method: "POST",
        body: JSON.stringify({ campaign_id, variations, language }),
      }, AI_REQUEST_TIMEOUT_MS),
    evaluate: (poster_id: string) =>
      req<PosterEvaluation>(`/posters/${poster_id}/evaluate`, { method: "POST" }, AI_REQUEST_TIMEOUT_MS),
  },

  adcopy: {
    // Calls the local Qwen model (loads from disk if not already resident) —
    // same class of slow GPU-bound call as poster generation/evaluation below,
    // so it needs the same long timeout instead of the 30s default.
    generate: (campaign_id: string, platforms: string[], tone = "professional", language?: string) =>
      req<AdCopy[]>("/adcopy/generate", {
        method: "POST",
        body: JSON.stringify({ campaign_id, platforms, tone, language }),
      }, AI_REQUEST_TIMEOUT_MS),
    getByCampaign: (campaign_id: string) =>
      req<AdCopy[]>(`/adcopy/${campaign_id}`),
  },

  posting: {
    publish: (data: PostRequest) =>
      req<SocialPost>("/posting/publish", { method: "POST", body: JSON.stringify(data) }),
    // Publishes to several platforms in one call, each on its own SocialPost
    // row — one platform failing never blocks or fails the others.
    publishCampaign: (campaign_id: string, data: CampaignPublishRequest) =>
      req<SocialPost[]>(`/posting/campaign/${campaign_id}/publish`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    getBycampaign: (campaign_id: string) =>
      req<SocialPost[]>(`/posting/campaign/${campaign_id}`),
    getStatus: (post_id: string) =>
      req<SocialPost>(`/posting/${post_id}`),
    retry: (post_id: string) =>
      req<SocialPost>(`/posting/retry/${post_id}`, { method: "POST" }),
    healthCheck: () => req<Record<string, boolean>>("/posting/health/platforms"),
    integrationsStatus: () =>
      req<Record<string, IntegrationStatus>>("/posting/integrations/status"),
    syncMetrics: (campaign_id: string) =>
      req<MetricsSyncResult>(`/posting/metrics/sync/${campaign_id}`, { method: "POST" }),
    runScheduled: () =>
      req<{ status: string; published: number }>("/posting/scheduled/run", { method: "POST" }),
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
    timeseries: (days = 14, campaign_id?: string) =>
      req<EngagementPoint[]>(
        `/analytics/engagement/timeseries?days=${days}` +
        (campaign_id ? `&campaign_id=${encodeURIComponent(campaign_id)}` : "")
      ),
    platforms: (days = 14, campaign_id?: string) =>
      req<PlatformBreakdown[]>(
        `/analytics/engagement/platforms?days=${days}` +
        (campaign_id ? `&campaign_id=${encodeURIComponent(campaign_id)}` : "")
      ),
    trackingStatus: (campaign_id?: string) =>
      req<TrackingStatus>(
        `/analytics/tracking/status` +
        (campaign_id ? `?campaign_id=${encodeURIComponent(campaign_id)}` : "")
      ),
  },

  n8n: {
    trigger: (campaign_id: string, steps: string[] = PIPELINE_STEPS) =>
      req<N8nResponse>("/n8n/trigger/campaign", {
        method: "POST",
        body: JSON.stringify({ campaign_id, steps }),
      }),
    // Polled on an interval — must bypass the GET cache to see live progress.
    status: (campaign_id: string) =>
      rawReq<N8nStatus>(`/n8n/status/${campaign_id}`),
  },

  brandKit: {
    get: (campaign_id: string) =>
      req<BrandKitInfo>(`/brand-kit/${campaign_id}`),
    // The backend merges rather than replaces, so omitting a field leaves the
    // stored value alone — callers can save just the language without wiping
    // the contact block.
    setMeta: (campaign_id: string, meta: BrandKitMeta) => {
      const form = new FormData();
      (Object.keys(meta) as (keyof BrandKitMeta)[]).forEach((k) => {
        const v = meta[k];
        if (v !== undefined && v !== null) form.append(k, v);
      });
      return req(`/brand-kit/${campaign_id}/meta`, { method: "POST", body: form });
    },
    uploadAsset: (campaign_id: string, asset_type: string, file: File) => {
      const form = new FormData();
      form.append("asset_type", asset_type);
      form.append("file", file);
      return req(`/brand-kit/${campaign_id}/upload`, { method: "POST", body: form });
    },
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
  metadata_?: {
    visual_url?: string;
    [key: string]: any;
  };
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
  // True when generation failed (twice) and this is hardcoded English
  // placeholder copy, not a real result in the requested language.
  fallback?: boolean;
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

export interface CampaignPublishRequest {
  platforms: string[];
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

export interface EngagementPoint {
  date: string;
  impressions: number;
  clicks: number;
  likes: number;
  reach: number;
  is_mock: boolean;
}

export interface PlatformBreakdown {
  platform: string;
  impressions: number;
  clicks: number;
  likes: number;
  shares: number;
  comments: number;
  reach: number;
  spend: number;
  ctr: number;
  engagement_rate: number;
  is_mock: boolean;
  last_synced_at: string | null;
}

export interface TrackingStatus {
  campaign_id: string | null;
  event_count: number;
  published_posts: number;
  mock_event_count: number;
  has_real_data: boolean;
  last_synced_at: string | null;
  last_event_at: string | null;
}

export interface IntegrationStatus {
  configured: boolean;
  healthy: boolean;
  mode: "live" | "mock";
}

export interface MetricsSyncResult {
  campaign_id: string;
  posts_checked: number;
  synced: number;
  failed: number;
  mock_sourced: number;
}

export interface N8nStatus {
  campaign_id: string;
  status: string;
  posts: { platform: string; status: string; is_mock: boolean }[];
}

/** Fields accepted by POST /brand-kit/{id}/meta. All optional — merged, not replaced. */
export interface BrandKitMeta {
  language?: string;
  brand_color_hex?: string;
  phone?: string;
  website?: string;
  address_en?: string;
  address_ta?: string;
}

export interface BrandKitInfo {
  campaign_id: string;
  logo?: string;
  partner_logo?: string;
  product?: string;
  product_cutout?: string;
  map_image?: string;
  font_regular?: string;
  font_bold?: string;
  language: string;
  brand_color_hex?: string;
  phone?: string;
  website?: string;
  address_en?: string;
  address_ta?: string;
  /** Which poster layout this kit qualifies for. Both are designed layouts. */
  layout: "designed" | "brochure";
  has_contact_details: boolean;
  has_brochure_assets: boolean;
}

/** Asset slots the upload endpoint accepts. */
export const BRAND_ASSET_SLOTS = [
  { key: "logo",           label: "Brand logo",     hint: "Shown in the header band" },
  { key: "partner_logo",   label: "Partner logo",   hint: "Optional second logo, header right" },
  { key: "product_cutout", label: "Product cutout", hint: "Transparent PNG — unlocks the brochure layout" },
  { key: "product",        label: "Product photo",  hint: "Used as the hero if no cutout is set" },
  { key: "map_image",      label: "Map / location", hint: "Thumbnail in the contact footer" },
] as const;
