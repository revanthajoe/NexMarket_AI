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
    preferred_platform: str = Field(..., pattern="^(instagram|facebook|linkedin|twitter|all)$")
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
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Poster ──────────────────────────────────────────────────────────────────

class PosterGenerateRequest(BaseModel):
    campaign_id: str
    variations: int = Field(1, ge=1, le=4)
    style_override: Optional[str] = None


class PosterRead(BaseModel):
    id: str
    campaign_id: str
    image_url: str
    prompt_used: Optional[str]
    provider: str
    variation_index: int
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
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Ad Copy ─────────────────────────────────────────────────────────────────

class AdCopyGenerateRequest(BaseModel):
    campaign_id: str
    platforms: List[str] = Field(
        default=["instagram", "facebook", "linkedin", "twitter", "email"]
    )
    tone: Optional[str] = "professional"


class AdCopyRead(BaseModel):
    id: str
    campaign_id: str
    platform: str
    headline: Optional[str]
    body: str
    cta_variants: Optional[List[str]]
    hashtags: Optional[List[str]]
    tone: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Sentiment ───────────────────────────────────────────────────────────────

class SentimentRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1)
    campaign_id: Optional[str] = None


class SentimentResultRead(BaseModel):
    text: str
    label: str
    positive_score: float
    negative_score: float
    neutral_score: float
    confidence: float
    model_used: str

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
    created_at: datetime

    model_config = {"protected_namespaces": ()}

    model_config = {"from_attributes": True}


# ─── Optimization ────────────────────────────────────────────────────────────

class OptimizationRequest(BaseModel):
    campaign_id: str
    budget: Optional[float] = None


class OptimizationRead(BaseModel):
    recommended_platform: str
    recommended_time: Optional[str]
    recommended_budget: Optional[float]
    confidence: float
    reasoning: Optional[str]
    platform_scores: Optional[Dict[str, float]]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Social Posting ──────────────────────────────────────────────────────────

class PostRequest(BaseModel):
    campaign_id: str
    platform: str = Field(..., pattern="^(instagram|facebook|linkedin|twitter)$")
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
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── n8n Webhook ─────────────────────────────────────────────────────────────

class N8nTriggerCampaign(BaseModel):
    campaign_id: str
    steps: List[str] = Field(
        default=["poster", "adcopy", "evaluate", "forecast", "optimize", "post"]
    )


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
