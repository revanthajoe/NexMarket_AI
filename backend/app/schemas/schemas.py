"""Pydantic v2 schemas — request/response contracts for all endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Campaign ────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    product_name: str = Field(..., min_length=2, max_length=255)
    description: str = Field(..., min_length=10)
    offer: str = Field(..., min_length=5, max_length=500)
    target_audience: str = Field(..., min_length=5, max_length=500)
    campaign_goal: str = Field(..., max_length=255)
    preferred_platform: str = Field(..., pattern="^(instagram|facebook|telegram|whatsapp|all)$")
    brand_style: Optional[str] = None
    budget: Optional[float] = Field(None, ge=0)
    post_schedule: Optional[datetime] = None


class CampaignRead(BaseModel):
    id: str
    name: str
    product_name: str
    description: str
    offer: str
    target_audience: str
    campaign_goal: str
    preferred_platform: str
    brand_style: Optional[str]
    budget: Optional[float]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignSummary(BaseModel):
    id: str
    name: str
    status: str
    preferred_platform: str
    product_name: str
    campaign_goal: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Poster ──────────────────────────────────────────────────────────────────

class PosterGenerateRequest(BaseModel):
    campaign_id: str
    variations: int = Field(1, ge=1, le=4)
    style_override: Optional[str] = None
    seed: Optional[int] = Field(
        None,
        description="Pin the SDXL seed to exactly reproduce a prior poster. Omit for a fresh deterministic-per-variation seed.",
    )
    language: Optional[str] = Field(
        None,
        description="Poster language code (en/hi/ta/te/mr/es/fr). Overrides the saved brand kit language for this request.",
    )


class PosterRead(BaseModel):
    id: str
    campaign_id: str
    parent_poster_id: Optional[str] = None
    image_url: str
    prompt_used: Optional[str]
    provider: str
    variation_index: int
    version: int = 1
    generation_reason: Optional[str] = None
    improvement_instruction: Optional[str] = None
    model_version_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PosterFeedbackCreate(BaseModel):
    feedback_type: str = Field(default="QUALITY", max_length=50)
    feedback_text: str = Field(..., min_length=1)
    source: str = Field(default="SYSTEM", max_length=50)
    score: Optional[float] = Field(None, ge=0, le=100)
    source_type: str = Field(default="UNKNOWN", max_length=20)
    source_system: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    model_version_id: Optional[str] = None
    is_fallback: Optional[bool] = None


class PosterFeedbackRead(BaseModel):
    id: str
    poster_id: str
    feedback_type: str
    feedback_text: str
    source: str
    score: Optional[float]
    source_type: str
    source_system: Optional[str]
    model_name: Optional[str]
    model_version: Optional[str]
    is_fallback: Optional[bool]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Poster Evaluation ───────────────────────────────────────────────────────

class PosterEvaluationRead(BaseModel):
    id: str
    poster_id: str
    overall_score: float
    readability_score: float
    layout_score: float
    branding_score: float
    contrast_score: float
    cta_score: float
    visual_appeal_score: float
    strengths: Optional[List[str]]
    weaknesses: Optional[List[str]]
    suggestions: Optional[List[str]]
    source_type: str
    source_system: Optional[str]
    model_name: Optional[str]
    model_version: Optional[str]
    is_fallback: Optional[bool]
    model_version_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Ad Copy ─────────────────────────────────────────────────────────────────

class AdCopyGenerateRequest(BaseModel):
    campaign_id: str
    platforms: List[str] = Field(
        default=["instagram", "facebook", "telegram", "whatsapp", "email"]
    )
    tone: Optional[str] = "professional"
    language: Optional[str] = Field(
        None,
        description="Ad copy language code (en/hi/ta/te/mr/es/fr). Falls back to the campaign's brand kit language.",
    )


class AdCopyRead(BaseModel):
    id: str
    campaign_id: str
    platform: str
    headline: Optional[str]
    body: str
    cta_variants: Optional[List[str]]
    hashtags: Optional[List[str]]
    tone: Optional[str]
    # True when Qwen's output failed to parse as JSON and this row is the
    # hardcoded English placeholder rather than a real generation result.
    fallback: bool = False
    source_type: str = "UNKNOWN"
    source_system: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    model_version_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Sentiment ───────────────────────────────────────────────────────────────

class SentimentRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1)
    campaign_id: Optional[str] = None
    source_type: str = Field(default="UNKNOWN", max_length=20)
    source_system: Optional[str] = None
    source_reference: Optional[str] = None


class SentimentResultRead(BaseModel):
    text: str
    label: str
    positive_score: float
    negative_score: float
    neutral_score: float
    confidence: float
    model_used: str
    source_type: str = "UNKNOWN"
    input_source_type: str = "UNKNOWN"
    source_system: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None

    model_config = {"protected_namespaces": ()}


class SentimentBatchResponse(BaseModel):
    results: List[SentimentResultRead]
    summary: Dict[str, int]


# ─── Lead Score ──────────────────────────────────────────────────────────────

class LeadScoreRequest(BaseModel):
    campaign_id: str
    lead_identifier: str
    clicks: int = Field(0, ge=0)
    views: int = Field(0, ge=0)
    time_spent_seconds: float = Field(0.0, ge=0)
    source_platform: str = "unknown"
    prior_purchases: int = Field(0, ge=0)
    device: str = "desktop"
    age_group: str = "25-34"
    location_tier: int = Field(1, ge=1, le=3)  # 1=metro, 2=city, 3=rural


class LeadScoreRead(BaseModel):
    score: float
    purchase_probability: float
    category: str
    feature_importance: Optional[Dict[str, float]]
    source_type: str = "UNKNOWN"
    source_system: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    is_fallback: Optional[bool] = None
    model_version_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Engagement Forecast ─────────────────────────────────────────────────────

class ForecastRequest(BaseModel):
    campaign_id: str
    horizon_days: int = Field(7, ge=1, le=30)


class ForecastRead(BaseModel):
    campaign_id: str
    forecast_horizon_days: int
    predicted_likes: List[float]
    predicted_shares: List[float]
    predicted_comments: List[float]
    predicted_ctr: List[float]
    predicted_reach: List[float]
    confidence_intervals: Optional[Dict[str, Any]]
    model_version: str
    source_type: str = "UNKNOWN"
    history_source: str = "UNKNOWN"
    source_reference: Optional[str] = None
    is_fallback: Optional[bool] = None
    model_version_id: Optional[str] = None
    created_at: datetime

    model_config = {
        "protected_namespaces": (),
        "from_attributes": True
    }


# ─── Optimization ────────────────────────────────────────────────────────────

class OptimizationRequest(BaseModel):
    campaign_id: str
    budget: Optional[float] = None


class OptimizationRead(BaseModel):
    id: Optional[str] = None
    campaign_id: Optional[str] = None
    recommended_platform: str
    recommended_time: Optional[str]
    recommended_budget: Optional[float]
    confidence: float
    reasoning: Optional[str]
    platform_scores: Optional[Dict[str, float]]
    source_type: str = "UNKNOWN"
    algorithm: Optional[str] = None
    policy_version: Optional[str] = None
    reward_source: Optional[str] = None
    analytics_reference: Optional[str] = None
    reward: Optional[float] = None
    bandit_updated: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Social Posting ──────────────────────────────────────────────────────────

# Kept in sync with posting_service.SUPPORTED_PLATFORMS. Telegram and WhatsApp
# were added here too — without it the pattern silently 422s a platform the
# adapter layer fully supports.
_PLATFORM_PATTERN = "^(instagram|facebook|telegram|whatsapp)$"


class PostRequest(BaseModel):
    campaign_id: str
    platform: str = Field(..., pattern=_PLATFORM_PATTERN)
    ad_copy_id: Optional[str] = None
    poster_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class CampaignPublishRequest(BaseModel):
    """Publish one campaign to several platforms in a single call."""

    platforms: List[str] = Field(..., min_length=1)
    ad_copy_id: Optional[str] = None
    poster_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class PostStatusRead(BaseModel):
    id: str
    campaign_id: str
    platform: str
    status: str
    platform_post_id: Optional[str]
    platform_url: Optional[str]
    scheduled_at: Optional[datetime]
    posted_at: Optional[datetime]
    retry_count: int
    error_message: Optional[str]
    is_mock: bool
    source_type: str
    source_system: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── n8n Webhook ─────────────────────────────────────────────────────────────

class N8nTriggerCampaign(BaseModel):
    campaign_id: str
    execution_id: Optional[str] = None
    steps: List[str] = Field(
        # Full pipeline order — each step only runs when its name is present.
        # Logical dependency order:
        #   poster  → evaluate (needs a poster to score)
        #   adcopy  → sentiment (analyses the generated ad text)
        #   lead_prediction → forecast → optimize → post
        default=[
            "poster",
            "evaluate",
            "adcopy",
            "sentiment",
            "lead_prediction",
            "forecast",
            "optimize",
            "post",
            "analytics",
            "reward_sync",
        ]
    )
    # Which platforms the "post" step publishes to. None (the default) falls
    # back to the campaign's own preferred_platform — existing callers,
    # including n8n/workflows/campaign_pipeline.json, send no `platforms` at
    # all and keep working exactly as before.
    platforms: Optional[List[str]] = None


class N8nWebhookResponse(BaseModel):
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


# ─── Analytics Dashboard ─────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_campaigns: int
    active_campaigns: int
    total_posts: int
    successful_posts: int
    avg_engagement_rate: float
    total_leads: int
    hot_leads: int
