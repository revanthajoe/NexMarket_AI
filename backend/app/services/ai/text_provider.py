"""
app/services/ai/text_provider.py
─────────────────────────────────
One place that decides which model writes marketing copy.

Governed by `AI_TEXT_PROVIDER` (formerly POSTER_PHASE_PROVIDER, still honoured).
Used by poster brochure copy, the SDXL scene spec, and ad copy.

Why this exists as its own module rather than living in poster_generator: ad
copy needs the same routing, and importing a function named `poster_phase_json`
from the poster generator into the ad generator would be a lie about what the
call does. The behaviour is identical; only the home and the name changed.

Why Gemini is the default: Qwen2.5-3B at 4-bit cannot produce usable
non-English output. For posters it rendered the brand name "Birla Opus Paints"
as "பிறந்த உபோஸ் பின்னர்" ("Born Opus After"). For ad copy it fails to emit
parseable JSON at all on Tamil — twice, even with a retry — so the request fell
through to a hardcoded English template and came back looking like a successful
English generation. Gemini's `response_mime_type="application/json"` removes
that failure mode outright.

Sentiment, lead scoring and forecasting are unaffected: they route through
different inference_manager methods and still follow LLM_PROVIDER.
"""
from __future__ import annotations

from app.core.config import settings


async def generate_marketing_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
) -> dict:
    """Generate structured JSON copy via whichever provider is configured."""
    if settings.AI_TEXT_PROVIDER == "gemini":
        from ai.llm.gemini_service import gemini_llm_service
        return await gemini_llm_service.generate_json(system_prompt, user_prompt, temperature)

    from ai.inference_manager import inference_manager
    return await inference_manager.generate_visual_spec(system_prompt, user_prompt, temperature)
