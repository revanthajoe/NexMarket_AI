from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.core.config import settings


def _provided_key(api_key: str | None, authorization: str | None) -> str | None:
    if api_key:
        return api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def require_n8n_access(
    x_n8n_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Authenticate privileged n8n calls without introducing a user model."""
    expected = settings.N8N_API_KEY
    supplied = _provided_key(x_n8n_api_key, authorization)
    if expected and supplied and secrets.compare_digest(supplied, expected):
        return
    if settings.APP_ENV == "development" and not expected:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid n8n API credentials are required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_app_api_key(
    x_app_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Authenticate frontend-facing calls to expensive/mutating routes.

    This is a shared perimeter secret, not per-user auth — there is no
    user/tenant model. It stops naive/automated abuse of a publicly
    reachable deployment, not a targeted attacker who inspects traffic,
    since the key also ships in the frontend's built JS bundle.
    """
    expected = settings.APP_API_KEY
    supplied = _provided_key(x_app_api_key, authorization)
    if expected and supplied and secrets.compare_digest(supplied, expected):
        return
    if settings.APP_ENV == "development" and not expected:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid API credentials are required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_telegram_webhook_secret(
    x_telegram_secret_token: str | None = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> None:
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if expected and x_telegram_secret_token and secrets.compare_digest(
        x_telegram_secret_token, expected
    ):
        return
    if settings.APP_ENV == "development" and not expected:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid Telegram webhook credentials are required",
    )
