"""Local model boundary for structured marketing copy."""
from __future__ import annotations

from app.core.config import settings


async def generate_marketing_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
) -> dict:
    """Generate structured JSON copy with the local Qwen model."""
    from ai.inference_manager import inference_manager
    return await inference_manager.generate_visual_spec(system_prompt, user_prompt, temperature)
