from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.models import (
    Campaign,
    ModelMetadata,
    ModelVersion,
    Poster,
    PosterEvaluation,
    TrainingDataset,
)
from app.services.sdxl_lora import (
    create_training_dataset,
    promote_lora_candidate,
    record_validation,
    rollback_lora_candidate,
    start_lora_training,
)


async def _campaign(db: AsyncSessionLocal) -> Campaign:
    campaign = Campaign(
        name="Phase 10 campaign",
        product_name="Phase 10 product",
        description="A real campaign for lifecycle tests",
        offer="Validated offer",
        target_audience="Test audience",
        campaign_goal="brand_awareness",
        preferred_platform="instagram",
        status="ready",
    )
    db.add(campaign)
    await db.flush()
    return campaign


@pytest.mark.asyncio
async def test_dataset_excludes_nonproduction_and_is_insufficient():
    async with AsyncSessionLocal() as db:
        campaign = await _campaign(db)
        real = Poster(
            campaign_id=campaign.id,
            image_url="/posters/real.png",
            prompt_used="real validated prompt",
            provider="local-sdxl-composed",
        )
        simulated = Poster(
            campaign_id=campaign.id,
            image_url="/posters/simulated.png",
            prompt_used="simulated prompt",
            provider="mock",
        )
        fallback = Poster(
            campaign_id=campaign.id,
            image_url="/posters/fallback.png",
            prompt_used="fallback prompt",
            provider="local-sdxl-composed",
        )
        db.add_all([real, simulated, fallback])
        await db.flush()
        db.add_all([
            PosterEvaluation(
                poster_id=real.id,
                overall_score=85,
                source_type="PREDICTED",
                is_fallback=False,
            ),
            PosterEvaluation(
                poster_id=fallback.id,
                overall_score=95,
                source_type="FALLBACK",
                is_fallback=True,
            ),
        ])
        await db.commit()

        dataset = await create_training_dataset(db, min_examples=2)

        assert dataset.status == "INSUFFICIENT_DATA"
        assert dataset.record_count == 1
        assert dataset.manifest["poster_ids"] == [real.id]
        assert simulated.id not in dataset.manifest["poster_ids"]
        assert fallback.id not in dataset.manifest["poster_ids"]


@pytest.mark.asyncio
async def test_training_validation_promotion_and_rollback_require_real_artifact(tmp_path: Path):
    class StubAdapter:
        def train(self, *, dataset, configuration):
            artifact = tmp_path / "adapter.safetensors"
            artifact.write_bytes(b"real test adapter")
            return str(artifact)

    async with AsyncSessionLocal() as db:
        model = ModelMetadata(
            name="Stable Diffusion XL",
            model_type="diffusion",
            framework="PyTorch",
        )
        db.add(model)
        await db.flush()
        baseline = ModelVersion(
            model_id=model.id,
            version="baseline-test",
            artifact_path="stabilityai/stable-diffusion-xl-base-1.0",
            source="HUGGINGFACE",
            status="ACTIVE",
        )
        dataset = TrainingDataset(
            name="sdxl_test",
            version="sdxl_test_v1",
            source="ACTUAL+VALIDATED_FEEDBACK",
            record_count=2,
            provenance_policy="ACTUAL_OR_PREDICTED_VALIDATED",
            status="READY",
            manifest={"poster_ids": ["poster-1", "poster-2"]},
        )
        db.add_all([baseline, dataset])
        await db.commit()

        run = await start_lora_training(db, dataset, adapter=StubAdapter())
        assert run.status == "COMPLETED"
        assert run.output_model_version_id is not None

        candidate = await db.get(ModelVersion, run.output_model_version_id)
        assert candidate.status == "VALIDATING"
        assert candidate.artifact_hash is not None
        assert len(candidate.artifact_hash) == 64

        with pytest.raises(ValueError, match="approved validation"):
            await promote_lora_candidate(db, candidate.id)

        await record_validation(
            db,
            candidate.id,
            validation_dataset_id=dataset.id,
            metrics={"generation_valid": True},
            baseline_comparison={"quality_delta": 1.0},
            passed=True,
        )
        promoted = await promote_lora_candidate(db, candidate.id)
        assert promoted.status == "ACTIVE"
        await db.refresh(baseline)
        assert baseline.status == "RETIRED"

        restored = await rollback_lora_candidate(db, candidate.id)
        assert restored.id == baseline.id
        assert restored.status == "ACTIVE"
        await db.refresh(candidate)
        assert candidate.status == "RETIRED"
