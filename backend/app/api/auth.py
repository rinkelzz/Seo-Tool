"""Simple bearer-token auth for single-user setup."""

from fastapi import Depends, Header, HTTPException, status

from backend.app.core.settings import Settings, get_settings


def require_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Validate Authorization: Bearer <token>."""
    expected = f"Bearer {settings.app_api_token}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
