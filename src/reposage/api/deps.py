"""FastAPI route dependencies: authentication, database sessions, and context headers."""

from fastapi import Header, HTTPException, status

from reposage.config import settings
from reposage.db.session import get_db


async def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    """Enforce API key authentication header on protected endpoints."""
    # If in local development with default key or matching key, permit access
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-API-Key header",
        )

    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid X-API-Key provided",
        )

    return x_api_key
