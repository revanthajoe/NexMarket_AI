"""
Central configuration — reads from environment / .env file.
All services import Settings from here; never read os.environ directly.
"""
from __future__ import annotations


from functools import lru_cache
from pathlib import Path
from typing import List, Literal

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
    IMAGE_PROVIDER: Literal["openai", "stability", "mock", "local"] = "mock"
    STABILITY_API_KEY: str = ""

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
    LINKEDIN_ACCESS_TOKEN: str = ""
    LINKEDIN_PERSON_URN: str = ""
    LINKEDIN_ORG_URN: str = ""
    TWITTER_API_KEY: str = ""
    TWITTER_API_SECRET: str = ""
    TWITTER_ACCESS_TOKEN: str = ""
    TWITTER_ACCESS_TOKEN_SECRET: str = ""

    # ── n8n ───────────────────────────────────────────────────────
    N8N_WEBHOOK_BASE: str = "http://localhost:5678/webhook"
    N8N_API_KEY: str = ""

    # ── Storage ───────────────────────────────────────────────────
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    POSTER_UPLOAD_DIR: str = "./assets/posters"
    STATIC_BASE_URL: str = "http://localhost:8000/static"
    SDXL_INFERENCE_STEPS: int = 28

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
