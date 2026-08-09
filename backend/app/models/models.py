"""
All SQLAlchemy ORM models for NexMarket AI.
Tables: campaigns, posters, ad_copies, poster_evaluations,
        social_posts, analytics_events, sentiment_results,
        lead_scores, engagement_forecasts, optimization_results.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Campaign
# ─────────────────────────────────────────────────────────────────────────────
class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    offer: Mapped[str] = mapped_column(String(500), nullable=False)
    target_audience: Mapped[str] = mapped_column(String(500), nullable=False)
    campaign_goal: Mapped[str] = mapped_column(String(255), nullable=False)
    preferred_platform: Mapped[str] = mapped_column(String(100), nullable=False)
    brand_style: Mapped[Optional[str]] = mapped_column(String(255))
    budget: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    # draft | generating | ready | posted | archived

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    posters: Mapped[list["Poster"]] = relationship(back_populates="campaign")
    ad_copies: Mapped[list["AdCopy"]] = relationship(back_populates="campaign")
    social_posts: Mapped[list["SocialPost"]] = relationship(back_populates="campaign")
    analytics: Mapped[list["AnalyticsEvent"]] = relationship(back_populates="campaign")
    lead_scores: Mapped[list["LeadScore"]] = relationship(back_populates="campaign")
    forecasts: Mapped[list["EngagementForecast"]] = relationship(
        back_populates="campaign"
    )
    optimizations: Mapped[list["OptimizationResult"]] = relationship(
        back_populates="campaign"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Poster
# ─────────────────────────────────────────────────────────────────────────────
class Poster(Base):
    __tablename__ = "posters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    image_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    prompt_used: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50), default="mock")
    variation_index: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="posters")
    evaluations: Mapped[list["PosterEvaluation"]] = relationship(
        back_populates="poster"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Poster Evaluation (Vision LLM)
# ─────────────────────────────────────────────────────────────────────────────
class PosterEvaluation(Base):
    __tablename__ = "poster_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poster_id: Mapped[str] = mapped_column(
        ForeignKey("posters.id", ondelete="CASCADE")
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    readability_score: Mapped[float] = mapped_column(Float, default=0.0)
    layout_score: Mapped[float] = mapped_column(Float, default=0.0)
    branding_score: Mapped[float] = mapped_column(Float, default=0.0)
    contrast_score: Mapped[float] = mapped_column(Float, default=0.0)
    cta_score: Mapped[float] = mapped_column(Float, default=0.0)
    visual_appeal_score: Mapped[float] = mapped_column(Float, default=0.0)
    strengths: Mapped[Optional[list]] = mapped_column(JSON)
    weaknesses: Mapped[Optional[list]] = mapped_column(JSON)
    suggestions: Mapped[Optional[list]] = mapped_column(JSON)
    raw_response: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    poster: Mapped["Poster"] = relationship(back_populates="evaluations")


# ─────────────────────────────────────────────────────────────────────────────
# Ad Copy
# ─────────────────────────────────────────────────────────────────────────────
class AdCopy(Base):
    __tablename__ = "ad_copies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    # instagram | facebook | linkedin | email | twitter
    headline: Mapped[Optional[str]] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta_variants: Mapped[Optional[list]] = mapped_column(JSON)
    hashtags: Mapped[Optional[list]] = mapped_column(JSON)
    tone: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="ad_copies")


# ─────────────────────────────────────────────────────────────────────────────
# Social Post
# ─────────────────────────────────────────────────────────────────────────────
class SocialPost(Base):
    __tablename__ = "social_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    ad_copy_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ad_copies.id", ondelete="SET NULL")
    )
    poster_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("posters.id", ondelete="SET NULL")
    )

    # Scheduling
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Status tracking
    status: Mapped[str] = mapped_column(String(50), default="pending")
    # pending | scheduled | posting | posted | failed | cancelled
    platform_post_id: Mapped[Optional[str]] = mapped_column(String(500))
    platform_url: Mapped[Optional[str]] = mapped_column(String(2048))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    response_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="social_posts")
    logs: Mapped[list["PostLog"]] = relationship(back_populates="post")


class PostLog(Base):
    """Append-only audit trail for every post action."""

    __tablename__ = "post_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    post_id: Mapped[str] = mapped_column(
        ForeignKey("social_posts.id", ondelete="CASCADE")
    )
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    post: Mapped["SocialPost"] = relationship(back_populates="logs")


# ─────────────────────────────────────────────────────────────────────────────
# Analytics Event
# ─────────────────────────────────────────────────────────────────────────────
class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(100))
    event_date: Mapped[datetime] = mapped_column(DateTime)
    impressions: Mapped[int] = mapped_column(BigInteger, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    reach: Mapped[int] = mapped_column(BigInteger, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    spend: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="analytics")


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment
# ─────────────────────────────────────────────────────────────────────────────
class SentimentResult(Base):
    __tablename__ = "sentiment_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(String(20))  # positive | negative | neutral
    positive_score: Mapped[float] = mapped_column(Float, default=0.0)
    negative_score: Mapped[float] = mapped_column(Float, default=0.0)
    neutral_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model_used: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# Lead Score
# ─────────────────────────────────────────────────────────────────────────────
class LeadScore(Base):
    __tablename__ = "lead_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    lead_identifier: Mapped[str] = mapped_column(String(500))
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0-100
    purchase_probability: Mapped[float] = mapped_column(Float, nullable=False)  # 0-1
    category: Mapped[str] = mapped_column(String(20))  # hot | warm | cold
    feature_importance: Mapped[Optional[dict]] = mapped_column(JSON)
    input_features: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="lead_scores")


# ─────────────────────────────────────────────────────────────────────────────
# Engagement Forecast (LSTM)
# ─────────────────────────────────────────────────────────────────────────────
class EngagementForecast(Base):
    __tablename__ = "engagement_forecasts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    forecast_horizon_days: Mapped[int] = mapped_column(Integer, default=7)
    predicted_likes: Mapped[Optional[list]] = mapped_column(JSON)
    predicted_shares: Mapped[Optional[list]] = mapped_column(JSON)
    predicted_comments: Mapped[Optional[list]] = mapped_column(JSON)
    predicted_ctr: Mapped[Optional[list]] = mapped_column(JSON)
    predicted_reach: Mapped[Optional[list]] = mapped_column(JSON)
    confidence_intervals: Mapped[Optional[dict]] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(50), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="forecasts")


# ─────────────────────────────────────────────────────────────────────────────
# Campaign Optimization
# ─────────────────────────────────────────────────────────────────────────────
class OptimizationResult(Base):
    __tablename__ = "optimization_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    recommended_platform: Mapped[str] = mapped_column(String(100))
    recommended_time: Mapped[Optional[str]] = mapped_column(String(100))
    recommended_budget: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    platform_scores: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="optimizations")
