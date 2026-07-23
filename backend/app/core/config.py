"""
Central configuration — reads from environment / .env file.
All services import Settings from here; never read os.environ directly.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    # ── LLM ───────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["openai", "gemini"] = "openai"
    LLM_MODEL: str = "gpt-4o"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # ── Image Generation ──────────────────────────────────────────
    IMAGE_PROVIDER: Literal["openai", "stability", "mock"] = "mock"
    STABILITY_API_KEY: str = ""

    # ── Vision LLM ────────────────────────────────────────────────
    VISION_PROVIDER: Literal["openai", "gemini"] = "openai"
    VISION_MODEL: str = "gpt-4o"

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

    # ── ML ────────────────────────────────────────────────────────
    LSTM_MODEL_PATH: str = "./ml/lstm/engagement_lstm.h5"
    XGBOOST_MODEL_PATH: str = "./ml/xgboost_model/lead_model.json"
    SENTIMENT_MODEL: str = "distilbert-base-uncased-finetuned-sst-2-english"

    @property
    def is_demo(self) -> bool:
        return self.APP_ENV == "development" and not self.OPENAI_API_KEY


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
