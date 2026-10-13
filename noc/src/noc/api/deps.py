import hmac
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from noc.config import Settings


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


def require_token(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.api_token
    if expected is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "NOC_API_TOKEN is not configured")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, expected.get_secret_value()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
