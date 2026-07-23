"""JWT token creation and validation."""

import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

import jwt
from jwt import PyJWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from geocare.config.settings import settings
from geocare.config.container import container
from geocare.domain.entities.user import User, UserRole, UserStatus
from geocare.domain.ports.repositories import UserRepository


# Token types
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    access_token: Optional[str] = Depends(oauth2_scheme),
    user_repo: UserRepository = Depends(container.infrastructure.repositories.user_repository),
) -> User:
    """Get current authenticated user from JWT token."""
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(access_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
    except PyJWTError:
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
    return Depends(role_checker)


# Common role dependencies
require_admin = require_role(UserRole.ADMIN)
require_analyst = require_role(UserRole.ADMIN, UserRole.ANALYST)
require_viewer = require_role(UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER)


def create_access_token(
    subject: str,
    roles: List[str],
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a short-lived access token.

    Args:
        subject: User ID (UUID string)
        roles: List of user roles
        expires_delta: Optional custom expiration
        additional_claims: Additional claims to include

    Returns:
        Encoded JWT string
    """
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    claims = {
        "sub": subject,
        "roles": roles,
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(time.time()),
        "exp": int(expire.timestamp()),
    }

    if additional_claims:
        claims.update(additional_claims)

    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a long-lived refresh token.

    Args:
        subject: User ID (UUID string)
        expires_delta: Optional custom expiration

    Returns:
        Encoded JWT string
    """
    expire = datetime.utcnow() + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))

    claims = {
        "sub": subject,
        "type": REFRESH_TOKEN_TYPE,
        "iat": int(time.time()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT string

    Returns:
        Decoded claims dictionary

    Raises:
        PyJWTError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise PyJWTError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise PyJWTError(f"Invalid token: {str(e)}")


def get_token_expiry(token: str) -> Optional[datetime]:
    """Get token expiration time without full validation."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(exp)
    except Exception:
        pass
    return None


def is_token_expired(token: str) -> bool:
    """Check if token is expired without raising."""
    try:
        decode_token(token)
        return False
    except PyJWTError:
        return True


def get_token_type(token: str) -> Optional[str]:
    """Get token type (access/refresh) without full validation."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        return payload.get("type")
    except Exception:
        return None


def refresh_access_token(refresh_token: str) -> tuple[str, str]:
    """
    Create new access and refresh tokens from a valid refresh token.

    Args:
        refresh_token: Valid refresh token

    Returns:
        Tuple of (new_access_token, new_refresh_token)

    Raises:
        PyJWTError: If refresh token is invalid
    """
    payload = decode_token(refresh_token)

    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise PyJWTError("Invalid token type for refresh")

    subject = payload.get("sub")
    if not subject:
        raise PyJWTError("Invalid refresh token: missing subject")

    # Get roles from refresh token or fetch from DB
    roles = payload.get("roles", ["viewer"])

    # Create new token pair
    new_access = create_access_token(subject=subject, roles=roles)
    new_refresh = create_refresh_token(subject=subject)

    return new_access, new_refresh


# Token types
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"