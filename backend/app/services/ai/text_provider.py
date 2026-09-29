from app.core.config import settings


import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

async def generate_marketing_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
) -> dict:
    """Generate structured JSON copy."""
    provider = getattr(settings, "AI_TEXT_PROVIDER", "local")

    if provider == "openai" and settings.OPENAI_API_KEY:
        import openai
        try:
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            content = resp.choices[0].message.content
            return json.loads(content)
        except Exception as exc:
            logger.error(f"OpenAI generation failed: {exc}")
            raise

    from ai.inference_manager import inference_manager
    return await inference_manager.generate_visual_spec(system_prompt, user_prompt, temperature)
