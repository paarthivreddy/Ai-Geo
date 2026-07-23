"""Authentication API routes."""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm  # noqa: F401  (kept for OAuth2 token endpoint compat)
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.config.container import container
from geocare.config.settings import settings
from geocare.domain.entities.user import User, UserRole, UserStatus
from geocare.domain.ports.repositories import UserRepository
from geocare.infrastructure.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from geocare.presentation.api.deps import (
    get_current_user,
    require_admin,
    require_analyst,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# Request/Response Models
class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole = UserRole.VIEWER


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    status: UserStatus
    last_login_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Routes
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: UserCreateRequest,
    user_repo: UserRepository = Depends(lambda: container.infrastructure.repositories.user_repository()),
) -> User:
    """Register a new user (admin only in production)."""
    # Check if user exists
    existing = await user_repo.get_by_email(request.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Hash password
    password_hash, salt = hash_password(request.password)

    # Create user
    user = User(
        email=request.email,
        password_hash=password_hash,
        full_name=request.full_name,
        role=request.role,
        salt=salt,
    )

    return await user_repo.create(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    response: Response,
    request: LoginRequest,
    user_repo: UserRepository = Depends(lambda: container.infrastructure.repositories.user_repository()),
) -> TokenResponse:
    """Login with email and password (JSON body), return JWT tokens."""
    user = await user_repo.get_by_email(request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or locked",
        )

    if not verify_password(request.password, user.password_hash):
        # Increment failed attempts
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.status = UserStatus.LOCKED
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        await user_repo.update(user)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.last_login_at = datetime.utcnow()
    await user_repo.update(user)

    # Generate tokens
    access_token = create_access_token(
        subject=str(user.id),
        roles=[user.role.value],
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    # Set secure cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    request: TokenRefreshRequest,
    user_repo: UserRepository = Depends(lambda: container.infrastructure.repositories.user_repository()),
) -> TokenResponse:
    """Refresh access token using refresh token."""
    try:
        payload = decode_token(request.refresh_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await user_repo.get(UUID(user_id))
    if not user or not user.is_active():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Generate new tokens (rotate refresh token)
    access_token = create_access_token(
        subject=str(user.id),
        roles=[user.role.value],
    )
    new_refresh_token = create_refresh_token(subject=str(user.id))

    # Set new cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Logout - clear cookies."""
    response.delete_cookie("access_token", httponly=True, secure=not settings.DEBUG, samesite="strict")
    response.delete_cookie("refresh_token", httponly=True, secure=not settings.DEBUG, samesite="strict")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user profile."""
    return current_user


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    limit: int = 50,
    offset: int = 0,
    role: Optional[UserRole] = None,
    current_user: User = Depends(require_admin),
    user_repo: UserRepository = Depends(container.infrastructure.repositories.user_repository),
) -> list[User]:
    """List all users (admin only)."""
    return await user_repo.list(limit=limit, offset=offset, role=role.value if role else None)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(require_admin),
    user_repo: UserRepository = Depends(container.infrastructure.repositories.user_repository),
) -> User:
    """Get user by ID (admin only)."""
    user = await user_repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    full_name: Optional[str] = None,
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    current_user: User = Depends(require_admin),
    user_repo: UserRepository = Depends(container.infrastructure.repositories.user_repository),
) -> User:
    """Update user (admin only)."""
    user = await user_repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if full_name is not None:
        user.full_name = full_name
    if role is not None:
        user.role = role
    if status is not None:
        user.status = status

    return await user_repo.update(user)