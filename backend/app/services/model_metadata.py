"""Idempotent database registration for the runtime model registry."""
from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.model_registry import ModelSpec, REGISTRY
from app.models.models import ModelMetadata, ModelVersion

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_MODEL_NAMES = {
    "qwen_llm": "Qwen2.5-3B-Instruct",
    "qwen_vl": "Qwen2.5-VL-3B-Instruct",
    "sdxl": "Stable Diffusion XL",
    "distilbert": "DistilBERT SST-2",
    "xgboost": "XGBoost",
    "lstm": "PyTorch LSTM",
}


def _artifact_metadata(spec: ModelSpec) -> tuple[str | None, str | None, str]:
    if not spec.model_id.startswith("local://"):
        return None, None, "HUGGINGFACE"

    relative = spec.model_id.removeprefix("local://")
    path = (_BACKEND_ROOT / relative).resolve()
    if not path.is_file():
        return str(path), None, "UNKNOWN"

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return str(path), digest, "LOCAL_ARTIFACT"


def _version_for(spec: ModelSpec) -> str:
    return "artifact" if spec.model_id.startswith("local://") else "configured"


async def register_runtime_models(db: AsyncSession) -> dict[str, str]:
    """Register the current runtime registry without creating duplicates."""
    version_ids: dict[str, str] = {}
    for registry_key, spec in REGISTRY.items():
        name = _MODEL_NAMES.get(registry_key, registry_key)
        model = (await db.execute(
            select(ModelMetadata).where(ModelMetadata.name == name)
        )).scalar_one_or_none()
        if model is None:
            model = ModelMetadata(
                name=name,
                model_type=spec.model_type,
                framework="PyTorch" if spec.model_type in {"causal_lm", "vision_lm", "diffusion", "classifier", "lstm"} else "XGBoost" if spec.model_type == "xgboost" else "Python",
                description=spec.description,
            )
            db.add(model)
            await db.flush()

        version = _version_for(spec)
        existing = (await db.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == model.id,
                ModelVersion.version == version,
            )
        )).scalar_one_or_none()
        artifact_path, artifact_hash, source = _artifact_metadata(spec)
        if existing is None:
            existing = ModelVersion(
                model_id=model.id,
                version=version,
                artifact_path=artifact_path or spec.model_id,
                artifact_hash=artifact_hash,
                source=source,
                framework=model.framework,
                configuration={
                    "registry_key": registry_key,
                    "model_id": spec.model_id,
                    "model_type": spec.model_type,
                    "use_4bit": spec.use_4bit,
                },
                status="ACTIVE",
            )
            db.add(existing)
            await db.flush()
        version_ids[registry_key] = existing.id

    await db.commit()
    return version_ids


async def active_model_version_id(db: AsyncSession, registry_key: str) -> str | None:
    name = _MODEL_NAMES.get(registry_key, registry_key)
    result = await db.execute(
        select(ModelVersion.id)
        .join(ModelMetadata, ModelMetadata.id == ModelVersion.model_id)
        .where(ModelMetadata.name == name, ModelVersion.status == "ACTIVE")
        .order_by(ModelVersion.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
