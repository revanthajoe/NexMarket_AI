"""
Central configuration — reads from environment / .env file.
All services import Settings from here; never read os.environ directly.
"""
from __future__ import annotations


from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    # ── Security ──────────────────────────────────────────────────
    SECRET_KEY: str = "insecure-dev-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Database ──────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://nexmarket:nexmarket@localhost:5432/nexmarket_db"
    SYNC_DATABASE_URL: str = "postgresql://nexmarket:nexmarket@localhost:5432/nexmarket_db"
    USE_SQLITE_FALLBACK: bool = True
    SQLITE_DB_PATH: str = "./nexmarket.db"

    def _sqlite_path(self) -> str:
        return Path(self.SQLITE_DB_PATH).expanduser().resolve().as_posix()

    @property
    def effective_database_url(self) -> str:
        if self.APP_ENV == "development" and self.USE_SQLITE_FALLBACK:
            if self.DATABASE_URL.startswith(("postgresql://", "postgresql+asyncpg://")):
                return f"sqlite+aiosqlite:///{self._sqlite_path()}"
        return self.DATABASE_URL

    @property
    def effective_sync_database_url(self) -> str:
        if self.APP_ENV == "development" and self.USE_SQLITE_FALLBACK:
            if self.SYNC_DATABASE_URL.startswith(("postgresql://", "postgresql+asyncpg://")):
                return f"sqlite:///{self._sqlite_path()}"
        return self.SYNC_DATABASE_URL

    @property
    def is_sqlite(self) -> bool:
        return self.effective_database_url.startswith("sqlite+")

    # ── LLM ───────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["openai", "gemini", "local"] = "openai"
    LLM_MODEL: str = "gpt-4o"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LOCAL_LLM_BASE_URL: str = "http://localhost:11434/v1"

    # ── Image Generation ──────────────────────────────────────────
    # "local"  → SDXL background art + deterministic composer typesetting
    # "gemini" → Gemini renders the complete poster, text included (no composer)
    IMAGE_PROVIDER: Literal["openai", "stability", "mock", "local", "gemini"] = "mock"
    STABILITY_API_KEY: str = ""
    GEMINI_IMAGE_MODEL: str = "gemini-2.5-flash-image"

    # ── Generative text/vision provider ───────────────────────────
    # Which models write marketing COPY and score posters: poster brochure copy,
    # the SDXL scene spec, poster evaluation, and ad copy.
    #
    # Deliberately separate from LLM_PROVIDER / VISION_PROVIDER: those still
    # govern sentiment, lead scoring, forecasting and anything else, so flipping
    # this does not drag the whole system onto a cloud provider.
    #
    # "gemini" exists because Qwen2.5-3B at 4-bit cannot produce usable
    # non-English output. For posters it translated the brand name "Birla Opus
    # Paints" into "பிறந்த உபோஸ் பின்னர்" ("Born Opus After"); for ad copy it
    # fails to emit parseable JSON at all on Tamil and silently fell back to a
    # hardcoded English template.
    #
    # Was POSTER_PHASE_PROVIDER while it only governed the poster phase; the old
    # name is still read (see AI_TEXT_PROVIDER validator below) so existing .env
    # files keep working.
    AI_TEXT_PROVIDER: Literal["gemini", "local"] = "gemini"
    POSTER_PHASE_PROVIDER: Optional[Literal["gemini", "local"]] = None
    GEMINI_TEXT_MODEL: str = "gemini-3.5-flash"

    @model_validator(mode="after")
    def _honour_legacy_provider_name(self) -> "Settings":
        # An existing .env that only sets the old name must keep working. Only
        # applies when AI_TEXT_PROVIDER was left at its default, so an explicit
        # new-name setting always wins.
        if self.POSTER_PHASE_PROVIDER is not None and "AI_TEXT_PROVIDER" not in self.model_fields_set:
            object.__setattr__(self, "AI_TEXT_PROVIDER", self.POSTER_PHASE_PROVIDER)
        return self

    # ── Vision LLM ────────────────────────────────────────────────
    VISION_PROVIDER: Literal["openai", "gemini", "local"] = "openai"
    VISION_MODEL: str = "gpt-4o"
    LOCAL_VISION_BASE_URL: str = "http://localhost:11434/v1"

    # ── Social Media ──────────────────────────────────────────────
    SOCIAL_MODE: Literal["live", "mock"] = "mock"
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_ACCESS_TOKEN: str = ""
    META_IG_USER_ID: str = ""
    META_PAGE_ID: str = ""
    # Telegram Bot API. The one live platform that needs no public media URL —
    # its adapter uploads the poster bytes directly (see _resolve_local_media).
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # WhatsApp Business Cloud API. Business message distribution, not broadcast
    # publishing: every send targets one recipient number.
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_RECIPIENT: str = ""

    # Base URL social platforms fetch generated posters from. Falls back to
    # STATIC_BASE_URL when unset.
    #
    # Instagram, Facebook and WhatsApp all fetch the image server-side, so in
    # SOCIAL_MODE=live this MUST be publicly reachable — a localhost URL will
    # fail. Point it at a tunnel (ngrok/cloudflared) or real hosting. Telegram
    # is exempt: it uploads bytes directly. Mock mode is unaffected.
    PUBLIC_MEDIA_BASE_URL: str = ""

    @property
    def effective_media_base_url(self) -> str:
        return self.PUBLIC_MEDIA_BASE_URL or self.STATIC_BASE_URL

    # ── Posting worker ────────────────────────────────────────────
    # Publishes scheduled posts once they're due and pulls engagement back from
    # the platforms. Both loops are no-ops when there's nothing due to do.
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_SECONDS: int = 60
    METRICS_SYNC_INTERVAL_SECONDS: int = 900

    # ── n8n ───────────────────────────────────────────────────────
    N8N_WEBHOOK_BASE: str = "http://localhost:5678/webhook"
    N8N_API_KEY: str = ""

    # ── Storage ───────────────────────────────────────────────────
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    POSTER_UPLOAD_DIR: str = "./assets/posters"
    STATIC_BASE_URL: str = "http://localhost:8000/static"
    SDXL_INFERENCE_STEPS: int = 28
    SDXL_LORA_PATH: str = "./ml/lora/sdxl_poster_lora.safetensors"

    # ── ML ────────────────────────────────────────────────────────
    LSTM_MODEL_PATH: str = "./ml/lstm/engagement_lstm.pt"
    XGBOOST_MODEL_PATH: str = "./ml/xgboost_model/lead_model.json"
    SENTIMENT_MODEL: str = "distilbert-base-uncased-finetuned-sst-2-english"

    @property
    def is_demo(self) -> bool:
        return self.APP_ENV == "development" and not self.OPENAI_API_KEY


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
