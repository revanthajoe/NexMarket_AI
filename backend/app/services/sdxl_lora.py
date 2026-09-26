"""Controlled SDXL LoRA adaptation lifecycle.

This module owns metadata and safety gates only. A training adapter may be
injected by a manual caller; this service never fabricates an artifact or
starts a scheduler-driven GPU job.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Protocol

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import (
    ModelMetadata,
    ModelValidation,
    ModelVersion,
    Poster,
    PosterEvaluation,
    PosterFeedback,
    TrainingDataset,
    TrainingRun,
)

_ALLOWED_PROVENANCE = {"ACTUAL", "PREDICTED"}
_EXCLUDED_PROVENANCE = {"SIMULATED", "FALLBACK", "UNKNOWN"}
_SDXL_NAME = "Stable Diffusion XL"


class LoraTrainingAdapter(Protocol):
    """Manual training boundary; implementations must return a real artifact."""

    def train(self, *, dataset: TrainingDataset, configuration: dict) -> str:
        ...


@dataclass(frozen=True)
class EligibleCreativeExample:
    poster_id: str
    evaluation_ids: tuple[str, ...]
    feedback_ids: tuple[str, ...]
    created_at: datetime


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_hash(manifest: dict) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _is_allowed(source_type: Optional[str], is_fallback: Optional[bool]) -> bool:
    if is_fallback:
        return False
    return source_type in _ALLOWED_PROVENANCE


async def _eligible_examples(
    db: AsyncSession,
    *,
    cutoff: datetime,
) -> list[EligibleCreativeExample]:
    posters = (await db.execute(
        select(Poster).where(Poster.created_at <= cutoff).order_by(Poster.created_at.asc())
    )).scalars().all()
    examples: list[EligibleCreativeExample] = []

    for poster in posters:
        # Mock output is explicitly non-production training data. A real poster
        # can still have an AI evaluation: that evaluation is PREDICTED evidence,
        # never human ground truth.
        if poster.provider == "mock":
            continue
        evaluations = (await db.execute(
            select(PosterEvaluation).where(PosterEvaluation.poster_id == poster.id)
        )).scalars().all()
        feedback = (await db.execute(
            select(PosterFeedback).where(PosterFeedback.poster_id == poster.id)
        )).scalars().all()
        valid_evaluations = [
            item for item in evaluations
            if _is_allowed(item.source_type, item.is_fallback)
            and item.overall_score is not None
            and item.overall_score >= 70
        ]
        valid_feedback = [
            item for item in feedback
            if _is_allowed(item.source_type, item.is_fallback)
            and (item.score is None or item.score >= 70)
        ]
        if not valid_evaluations and not valid_feedback:
            continue
        examples.append(EligibleCreativeExample(
            poster_id=poster.id,
            evaluation_ids=tuple(item.id for item in valid_evaluations),
            feedback_ids=tuple(item.id for item in valid_feedback),
            created_at=poster.created_at,
        ))
    return examples


async def create_training_dataset(
    db: AsyncSession,
    *,
    name: str = "sdxl_marketing",
    cutoff: Optional[datetime] = None,
    min_examples: Optional[int] = None,
) -> TrainingDataset:
    """Snapshot eligible creative rows into a new immutable dataset version."""
    dataset_created_at = cutoff or datetime.utcnow()
    examples = await _eligible_examples(db, cutoff=dataset_created_at)
    previous = (await db.execute(
        select(TrainingDataset.version)
        .where(TrainingDataset.name == name)
        .order_by(desc(TrainingDataset.created_at))
        .limit(1)
    )).scalar_one_or_none()
    version_number = 1
    if previous:
        try:
            version_number = int(str(previous).rsplit("_v", 1)[1]) + 1
        except (IndexError, ValueError):
            version_number = 1
    version = f"{name}_v{version_number}"
    manifest = {
        "dataset_created_at": dataset_created_at.isoformat(),
        "eligibility_policy": "real_non_mock_poster_with_validated_quality_evidence_v1",
        "poster_ids": [item.poster_id for item in examples],
        "evaluation_ids": [item for example in examples for item in example.evaluation_ids],
        "feedback_ids": [item for example in examples for item in example.feedback_ids],
        "excluded_provenance": sorted(_EXCLUDED_PROVENANCE),
    }
    threshold = settings.SDXL_LORA_MIN_EXAMPLES if min_examples is None else min_examples
    status = "READY" if len(examples) >= threshold else "INSUFFICIENT_DATA"
    dataset = TrainingDataset(
        name=name,
        version=version,
        source="ACTUAL+VALIDATED_FEEDBACK",
        description="Immutable eligible SDXL creative-example manifest",
        record_count=len(examples),
        data_hash=_manifest_hash(manifest),
        provenance_policy="ACTUAL_OR_PREDICTED_VALIDATED",
        manifest=manifest,
        status=status,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def _sdxl_model(db: AsyncSession) -> ModelMetadata:
    rows = (await db.execute(
        select(ModelMetadata)
        .where(ModelMetadata.name == _SDXL_NAME)
        .order_by(ModelMetadata.created_at.asc())
    )).scalars().all()
    if rows:
        model = rows[0]
        if len(rows) > 1:
            for duplicate in rows[1:]:
                for version in duplicate.versions:
                    version.model_id = model.id
                await db.delete(duplicate)
            await db.flush()
        return model

    model = ModelMetadata(
        name=_SDXL_NAME,
        model_type="diffusion",
        framework="PyTorch",
        description="Stable Diffusion XL with optional validated LoRA adapters",
    )
    db.add(model)
    await db.flush()
    return model


async def active_sdxl_runtime(db: AsyncSession) -> tuple[Optional[str], Optional[str]]:
    """Return (active model-version ID, adapter path) for poster generation."""
    model = await _sdxl_model(db)
    version = (await db.execute(
        select(ModelVersion)
        .where(ModelVersion.model_id == model.id, ModelVersion.status == "ACTIVE")
        .order_by(desc(ModelVersion.created_at))
        .limit(1)
    )).scalar_one_or_none()
    if version is None:
        return None, None
    configuration = version.configuration or {}
    if configuration.get("adaptation") != "LoRA" or not version.artifact_path:
        return version.id, None
    artifact = Path(version.artifact_path)
    return version.id, str(artifact) if artifact.is_file() else None


async def start_lora_training(
    db: AsyncSession,
    dataset: TrainingDataset,
    *,
    adapter: Optional[LoraTrainingAdapter] = None,
    configuration: Optional[dict] = None,
) -> TrainingRun:
    """Record a manual training attempt; never reports completion without a file."""
    model = await _sdxl_model(db)
    run = TrainingRun(
        model_id=model.id,
        dataset_id=dataset.id,
        status="PENDING",
        configuration=configuration or {"method": "LoRA"},
    )
    db.add(run)
    await db.flush()
    if dataset.status == "INSUFFICIENT_DATA":
        run.status = "INSUFFICIENT_DATA"
        await db.commit()
        return run
    if adapter is None:
        run.status = "TRAINING_UNAVAILABLE"
        await db.commit()
        return run

    run.status = "RUNNING"
    run.started_at = datetime.utcnow()
    try:
        artifact = Path(adapter.train(dataset=dataset, configuration=run.configuration or {}))
        if not artifact.is_file():
            raise FileNotFoundError(f"LoRA adapter artifact does not exist: {artifact}")
        artifact_hash = _sha256_file(artifact)
        active = (await db.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == model.id,
                ModelVersion.status == "ACTIVE",
            ).order_by(desc(ModelVersion.created_at)).limit(1)
        )).scalar_one_or_none()
        candidate = ModelVersion(
            model_id=model.id,
            version=f"lora-{dataset.version}",
            artifact_path=str(artifact.resolve()),
            artifact_hash=artifact_hash,
            source="LOCAL_ARTIFACT",
            framework="PyTorch",
            configuration={
                **(run.configuration or {}),
                "adaptation": "LoRA",
                "dataset_id": dataset.id,
                "dataset_version": dataset.version,
                "base_model_version_id": active.id if active else None,
            },
            status="VALIDATING",
        )
        db.add(candidate)
        await db.flush()
        run.output_model_version_id = candidate.id
        run.status = "COMPLETED"
        run.completed_at = datetime.utcnow()
    except Exception as exc:
        run.status = "FAILED"
        run.completed_at = datetime.utcnow()
        run.metrics_summary = {"error": str(exc)}
    await db.commit()
    await db.refresh(run)
    return run


async def record_validation(
    db: AsyncSession,
    model_version_id: str,
    *,
    validation_dataset_id: Optional[str],
    metrics: dict,
    baseline_comparison: dict,
    passed: bool,
) -> ModelValidation:
    validation = ModelValidation(
        model_version_id=model_version_id,
        validation_dataset_id=validation_dataset_id,
        status="PASSED" if passed else "FAILED",
        validated_at=datetime.utcnow(),
        metrics=metrics,
        baseline_comparison=baseline_comparison,
        approval_status="APPROVED" if passed else "REJECTED",
    )
    db.add(validation)
    await db.commit()
    await db.refresh(validation)
    return validation


async def promote_lora_candidate(db: AsyncSession, candidate_id: str) -> ModelVersion:
    candidate = await db.get(ModelVersion, candidate_id)
    if candidate is None or candidate.status != "VALIDATING":
        raise ValueError("Only a VALIDATING SDXL candidate can be promoted")
    validation = (await db.execute(
        select(ModelValidation)
        .where(ModelValidation.model_version_id == candidate_id)
        .where(ModelValidation.status == "PASSED")
        .where(ModelValidation.approval_status == "APPROVED")
        .order_by(desc(ModelValidation.validated_at))
        .limit(1)
    )).scalar_one_or_none()
    if validation is None:
        raise ValueError("Candidate requires an approved validation before promotion")
    active = (await db.execute(
        select(ModelVersion).where(
            ModelVersion.model_id == candidate.model_id,
            ModelVersion.status == "ACTIVE",
        ).order_by(desc(ModelVersion.created_at)).limit(1)
    )).scalar_one_or_none()
    candidate.configuration = {
        **(candidate.configuration or {}),
        "previous_active_model_version_id": active.id if active else None,
    }
    candidate.status = "ACTIVE"
    await db.flush()
    if active and active.id != candidate.id:
        active.status = "RETIRED"
    await db.commit()
    await db.refresh(candidate)
    return candidate


async def rollback_lora_candidate(db: AsyncSession, candidate_id: str) -> ModelVersion:
    candidate = await db.get(ModelVersion, candidate_id)
    if candidate is None:
        raise ValueError("Unknown SDXL candidate")
    previous_id = (candidate.configuration or {}).get("previous_active_model_version_id")
    if not previous_id:
        raise ValueError("Candidate has no recoverable previous active version")
    previous = await db.get(ModelVersion, previous_id)
    if previous is None:
        raise ValueError("Previous SDXL version is unavailable")
    previous.status = "ACTIVE"
    candidate.status = "RETIRED"
    await db.commit()
    await db.refresh(previous)
    return previous
