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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Model metadata
# ─────────────────────────────────────────────────────────────────────────────
class ModelMetadata(Base):
    """Logical model family; runtime construction remains registry-owned."""

    __tablename__ = "model_metadata"
    __table_args__ = (UniqueConstraint("name", name="uq_model_metadata_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    framework: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list["ModelVersion"]] = relationship(
        back_populates="model", passive_deletes=True
    )
    training_runs: Mapped[list["TrainingRun"]] = relationship(
        back_populates="model", passive_deletes=True
    )


class ModelVersion(Base):
    """Traceability record for one runtime model/artifact registration."""

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version", name="uq_model_versions_model_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(
        ForeignKey("model_metadata.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    artifact_path: Mapped[Optional[str]] = mapped_column(String(1000))
    artifact_hash: Mapped[Optional[str]] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    framework: Mapped[Optional[str]] = mapped_column(String(100))
    configuration: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="REGISTERED")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    model: Mapped["ModelMetadata"] = relationship(back_populates="versions")
    training_runs: Mapped[list["TrainingRun"]] = relationship(
        back_populates="output_model_version", passive_deletes=True
    )
    validations: Mapped[list["ModelValidation"]] = relationship(
        back_populates="model_version", passive_deletes=True
    )


class TrainingDataset(Base):
    """Metadata only; dataset contents remain outside the database."""

    __tablename__ = "training_datasets"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_training_datasets_name_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    description: Mapped[Optional[str]] = mapped_column(Text)
    record_count: Mapped[Optional[int]] = mapped_column(Integer)
    data_hash: Mapped[Optional[str]] = mapped_column(String(128))
    provenance_policy: Mapped[Optional[str]] = mapped_column(String(50))
    manifest: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="REGISTERED")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    training_runs: Mapped[list["TrainingRun"]] = relationship(
        back_populates="dataset", passive_deletes=True
    )


class TrainingRun(Base):
    """Metadata for future training executions; no training is run here."""

    __tablename__ = "training_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(
        ForeignKey("model_metadata.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("training_datasets.id", ondelete="SET NULL")
    )
    output_model_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="REGISTERED")
    configuration: Mapped[Optional[dict]] = mapped_column(JSON)
    metrics_summary: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    model: Mapped["ModelMetadata"] = relationship(back_populates="training_runs")
    dataset: Mapped[Optional["TrainingDataset"]] = relationship(back_populates="training_runs")
    output_model_version: Mapped[Optional["ModelVersion"]] = relationship(
        back_populates="training_runs", foreign_keys=[output_model_version_id]
    )


class ModelValidation(Base):
    """Validation metadata without automatic approval or promotion."""

    __tablename__ = "model_validations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False
    )
    validation_dataset_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("training_datasets.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON)
    baseline_comparison: Mapped[Optional[dict]] = mapped_column(JSON)
    approval_status: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    model_version: Mapped["ModelVersion"] = relationship(back_populates="validations")


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

    # Relationships. `passive_deletes=True` on every one of these: each child's
    # FK is declared `ondelete="CASCADE"` (see e.g. Poster.campaign_id below),
    # but without this flag SQLAlchemy's ORM manages the delete itself first —
    # by default it tries to UPDATE each child's FK to NULL before the parent
    # DELETE, which fails outright with a NOT NULL constraint error on every
    # one of these (all are non-nullable). Confirmed live: turning on
    # `PRAGMA foreign_keys` (session.py) without this made `db.delete(campaign)`
    # raise IntegrityError instead of the silent-orphan behavior it replaced —
    # worse, not better. `passive_deletes=True` tells the ORM to leave deletion
    # of these children entirely to the database's own ON DELETE CASCADE.
    posters: Mapped[list["Poster"]] = relationship(back_populates="campaign", passive_deletes=True)
    ad_copies: Mapped[list["AdCopy"]] = relationship(back_populates="campaign", passive_deletes=True)
    social_posts: Mapped[list["SocialPost"]] = relationship(back_populates="campaign", passive_deletes=True)
    analytics: Mapped[list["AnalyticsEvent"]] = relationship(back_populates="campaign", passive_deletes=True)
    lead_scores: Mapped[list["LeadScore"]] = relationship(back_populates="campaign", passive_deletes=True)
    forecasts: Mapped[list["EngagementForecast"]] = relationship(
        back_populates="campaign", passive_deletes=True
    )
    optimizations: Mapped[list["OptimizationResult"]] = relationship(
        back_populates="campaign", passive_deletes=True
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
    parent_poster_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("posters.id", ondelete="SET NULL")
    )
    image_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    prompt_used: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50), default="mock")
    variation_index: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    generation_reason: Mapped[Optional[str]] = mapped_column(String(100))
    improvement_instruction: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    model_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="posters")
    parent_poster: Mapped[Optional["Poster"]] = relationship(
        "Poster",
        remote_side="Poster.id",
        back_populates="children",
    )
    children: Mapped[list["Poster"]] = relationship(
        "Poster",
        back_populates="parent_poster",
        passive_deletes=True,
    )
    # passive_deletes=True: poster_evaluations.poster_id is ondelete="CASCADE"
    # and non-nullable — same reasoning as the Campaign relationships above.
    evaluations: Mapped[list["PosterEvaluation"]] = relationship(
        back_populates="poster", passive_deletes=True
    )
    feedback: Mapped[list["PosterFeedback"]] = relationship(
        back_populates="poster", passive_deletes=True
    )


class PosterFeedback(Base):
    __tablename__ = "poster_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poster_id: Mapped[str] = mapped_column(ForeignKey("posters.id", ondelete="CASCADE"))
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False, default="QUALITY")
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    score: Mapped[Optional[float]] = mapped_column(Float)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    source_system: Mapped[Optional[str]] = mapped_column(String(100))
    model_name: Mapped[Optional[str]] = mapped_column(String(200))
    model_version: Mapped[Optional[str]] = mapped_column(String(100))
    is_fallback: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    poster: Mapped["Poster"] = relationship(back_populates="feedback")


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
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    source_system: Mapped[Optional[str]] = mapped_column(String(100))
    model_name: Mapped[Optional[str]] = mapped_column(String(200))
    model_version: Mapped[Optional[str]] = mapped_column(String(100))
    is_fallback: Mapped[Optional[bool]] = mapped_column(Boolean)
    model_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
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
    # instagram | facebook | telegram | whatsapp | email
    headline: Mapped[Optional[str]] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta_variants: Mapped[Optional[list]] = mapped_column(JSON)
    hashtags: Mapped[Optional[list]] = mapped_column(JSON)
    tone: Mapped[Optional[str]] = mapped_column(String(100))
    # True when Qwen's output failed to parse as JSON (twice — see
    # ad_generator.py's retry) and this is the hardcoded English placeholder
    # template instead of a real generation result. Same provenance-flag
    # convention as analytics_events.is_mock: without it, a failed non-English
    # request is indistinguishable from a real translated one.
    fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    source_system: Mapped[Optional[str]] = mapped_column(String(100))
    model_name: Mapped[Optional[str]] = mapped_column(String(200))
    model_version: Mapped[Optional[str]] = mapped_column(String(100))
    model_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
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
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    source_system: Mapped[Optional[str]] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="social_posts")
    # passive_deletes=True: post_logs.post_id is ondelete="CASCADE" and
    # non-nullable — same reasoning as the Campaign relationships above.
    logs: Mapped[list["PostLog"]] = relationship(back_populates="post", passive_deletes=True)


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
    # True when the numbers came from the mock adapter rather than a platform
    # API — the UI labels these so demo data is never read as measured results.
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    source_system: Mapped[Optional[str]] = mapped_column(String(100))
    source_reference: Mapped[Optional[str]] = mapped_column(String(500))
    # Set on every metrics sync so the UI can show how fresh the data is.
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
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
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    input_source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    source_system: Mapped[Optional[str]] = mapped_column(String(100))
    source_reference: Mapped[Optional[str]] = mapped_column(String(500))
    model_name: Mapped[Optional[str]] = mapped_column(String(200))
    model_version: Mapped[Optional[str]] = mapped_column(String(100))
    model_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
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
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    source_system: Mapped[Optional[str]] = mapped_column(String(100))
    model_name: Mapped[Optional[str]] = mapped_column(String(200))
    model_version: Mapped[Optional[str]] = mapped_column(String(100))
    is_fallback: Mapped[Optional[bool]] = mapped_column(Boolean)
    model_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
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
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    history_source: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    source_reference: Mapped[Optional[str]] = mapped_column(String(500))
    is_fallback: Mapped[Optional[bool]] = mapped_column(Boolean)
    model_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
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
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    algorithm: Mapped[Optional[str]] = mapped_column(String(200))
    policy_version: Mapped[Optional[str]] = mapped_column(String(100))
    reward_source: Mapped[Optional[str]] = mapped_column(String(20))
    analytics_reference: Mapped[Optional[str]] = mapped_column(String(500))
    reward: Mapped[Optional[float]] = mapped_column(Float)
    bandit_updated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="optimizations")
