import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.security import (
    require_app_api_key,
    require_n8n_access,
    require_telegram_webhook_secret,
)
from app.services.ai.brand_kit import validate_asset_bytes


def test_production_settings_reject_placeholder_secrets():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="insecure-dev-key-change-me",
            N8N_API_KEY="n" * 40,
            TELEGRAM_WEBHOOK_SECRET="t" * 20,
            USE_SQLITE_FALLBACK=False,
        )


def test_production_settings_accept_strong_secrets():
    settings = Settings(
        APP_ENV="production",
        SECRET_KEY="s" * 40,
        N8N_API_KEY="n" * 40,
        TELEGRAM_WEBHOOK_SECRET="t" * 20,
        APP_API_KEY="a" * 40,
        USE_SQLITE_FALLBACK=False,
    )
    assert settings.APP_ENV == "production"


def test_production_settings_reject_missing_app_api_key():
    with pytest.raises(ValueError, match="APP_API_KEY"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="s" * 40,
            N8N_API_KEY="n" * 40,
            TELEGRAM_WEBHOOK_SECRET="t" * 20,
            APP_API_KEY="",
            USE_SQLITE_FALLBACK=False,
        )


def test_sqlite_fallback_is_opt_in():
    assert Settings.model_fields["USE_SQLITE_FALLBACK"].default is False
    settings = Settings(
        APP_ENV="development",
        DATABASE_URL="postgresql+asyncpg://user@localhost/nexmarket",
        SYNC_DATABASE_URL="postgresql://user@localhost/nexmarket",
        USE_SQLITE_FALLBACK=False,
    )
    assert settings.effective_database_url.startswith("postgresql+asyncpg://")
    assert settings.effective_sync_database_url.startswith("postgresql://")


@pytest.mark.asyncio
async def test_n8n_access_rejects_invalid_key(monkeypatch):
    from app.core import security

    monkeypatch.setattr(security.settings, "APP_ENV", "production")
    monkeypatch.setattr(security.settings, "N8N_API_KEY", "expected")
    with pytest.raises(HTTPException) as exc:
        await require_n8n_access("wrong", None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_app_api_key_rejects_missing_and_accepts_valid_key(monkeypatch):
    from app.core import security

    monkeypatch.setattr(security.settings, "APP_ENV", "production")
    monkeypatch.setattr(security.settings, "APP_API_KEY", "expected")
    with pytest.raises(HTTPException) as exc:
        await require_app_api_key(None, None)
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException):
        await require_app_api_key("wrong", None)
    await require_app_api_key("expected", None)


@pytest.mark.asyncio
async def test_telegram_secret_is_required_when_configured(monkeypatch):
    from app.core import security

    monkeypatch.setattr(security.settings, "APP_ENV", "production")
    monkeypatch.setattr(security.settings, "TELEGRAM_WEBHOOK_SECRET", "telegram-secret")
    with pytest.raises(HTTPException) as exc:
        await require_telegram_webhook_secret("wrong")
    assert exc.value.status_code == 401
    await require_telegram_webhook_secret("telegram-secret")


def test_brand_asset_signature_validation_rejects_mismatched_content():
    with pytest.raises(ValueError, match="PNG signature"):
        validate_asset_bytes("logo", b"not-an-image", "png")


def test_brand_asset_signature_validation_accepts_png():
    validate_asset_bytes("logo", b"\x89PNG\r\n\x1a\npayload", "png")
