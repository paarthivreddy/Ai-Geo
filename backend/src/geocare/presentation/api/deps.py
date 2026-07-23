"""API dependencies for authentication and authorization."""

from typing import Optional
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.config.container import container
from geocare.config.database import get_db_session
from geocare.config.settings import settings
from geocare.domain.entities.user import User, UserRole, UserStatus
from geocare.domain.ports.repositories import UserRepository
from geocare.infrastructure.security.jwt import decode_token


# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    token: Optional[str] = Depends(oauth2_scheme),
    user_repo: UserRepository = Depends(container.infrastructure.repositories.user_repository),
) -> User:
    """Get current authenticated user from JWT token."""
    # Try cookie first, then Authorization header
    token_value = access_token or token
    if not token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token_value)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = await user_repo.get(UUID(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or locked",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user (alias for clarity)."""
    return current_user


def require_role(*allowed_roles: UserRole):
    """Dependency factory for role-based access control."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


# Common role dependencies
require_admin = require_role(UserRole.ADMIN)
require_analyst = require_role(UserRole.ADMIN, UserRole.ANALYST)
require_viewer = require_role(UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER)


async def get_db() -> AsyncSession:
    """Get database session."""
    async with get_db_session() as session:
        yield session