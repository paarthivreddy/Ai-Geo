"""Admin API routes for system management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from geocare.config.container import container
from geocare.presentation.api.deps import get_current_user, require_admin
from geocare.domain.entities.user import User, UserRole, UserStatus

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


# Request/Response Models
class UserCreateRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: UserRole = UserRole.VIEWER


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: UserRole
    status: UserStatus
    last_login_at: Optional[str] = None
    created_at: str


class GeographyRefreshRequest(BaseModel):
    dataset: Optional[str] = None  # "pincode", "locality", "census", "osm", or None for all
    version: Optional[str] = None


class GeographyStatusResponse(BaseModel):
    dataset_name: str
    version: str
    status: str
    row_count: int
    loaded_at: str
    activated_at: Optional[str] = None


class SystemHealthResponse(BaseModel):
    database: str
    redis: str
    celery_workers: int
    queue_depth: dict
    disk_usage: dict


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    limit: int = 50,
    offset: int = 0,
    role: Optional[UserRole] = None,
    current_user: User = Depends(require_admin),
) -> list[UserResponse]:
    """List all users with pagination."""
    user_repo = container.infrastructure.repositories.user_repository
    users = await user_repo.list(limit=limit, offset=offset, role=role.value if role else None)

    return [
        UserResponse(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            status=u.status,
            last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: UserCreateRequest,
    current_user: User = Depends(require_admin),
) -> UserResponse:
    """Create a new user (admin only)."""
    import bcrypt

    user_repo = container.infrastructure.repositories.user_repository

    # Check if email exists
    existing = await user_repo.get_by_email(request.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Hash password
    salt = bcrypt.gensalt(rounds=12).decode()
    password_hash = bcrypt.hashpw(request.password.encode(), salt.encode()).decode()

    # Create user
    from geocare.domain.entities.user import User as UserEntity
    user = UserEntity(
        email=request.email,
        password_hash=password_hash,
        full_name=request.full_name,
        role=request.role,
        salt=salt,
    )
    await user_repo.create(user)

    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        created_at=user.created_at.isoformat(),
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    request: UserUpdateRequest,
    current_user: User = Depends(require_admin),
) -> UserResponse:
    """Update user details."""
    user_repo = container.infrastructure.repositories.user_repository

    user = await user_repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if request.full_name:
        user.full_name = request.full_name
    if request.role:
        user.role = request.role
    if request.status:
        user.status = request.status

    await user_repo.update(user)

    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        created_at=user.created_at.isoformat(),
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(require_admin),
) -> dict:
    """Delete a user (soft delete - set inactive)."""
    user_repo = container.infrastructure.repositories.user_repository

    user = await user_repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    user.status = UserStatus.INACTIVE
    await user_repo.update(user)

    return {"message": "User deactivated"}


@router.post("/geography/refresh")
async def refresh_geography(
    request: GeographyRefreshRequest,
    current_user: User = Depends(require_admin),
) -> dict:
    """Trigger geography data refresh."""
    geo_refresh_uc = container.application.geography_refresh_use_case

    # Run in background
    from geocare.infrastructure.queue.tasks import refresh_geography_task
    task = refresh_geography_task.delay(
        dataset=request.dataset,
        version=request.version,
    )

    return {
        "task_id": task.id,
        "message": "Geography refresh started",
        "dataset": request.dataset or "all",
    }


@router.get("/geography/status", response_model=list[GeographyStatusResponse])
async def get_geography_status(
    current_user: User = Depends(require_admin),
) -> list[GeographyStatusResponse]:
    """Get status of all geography datasets."""
    from geocare.infrastructure.persistence.repositories.geography_repo import DatasetVersionRepositoryImpl
    from geocare.config.database import get_db_session

    async with get_db_session() as session:
        repo = DatasetVersionRepositoryImpl(session)
        versions = await repo.list_all()

    return [
        GeographyStatusResponse(
            dataset_name=v.dataset_name,
            version=v.version,
            status=v.status,
            row_count=v.row_count,
            loaded_at=v.loaded_at.isoformat(),
            activated_at=v.activated_at.isoformat() if v.activated_at else None,
        )
        for v in versions
    ]


@router.get("/system/health", response_model=SystemHealthResponse)
async def get_system_health(
    current_user: User = Depends(require_admin),
) -> SystemHealthResponse:
    """Get system health status."""
    import redis
    import psutil
    from sqlalchemy import text
    from geocare.config.database import engine
    from geocare.config.settings import settings

    # Check database
    db_status = "healthy"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    # Check Redis
    redis_status = "healthy"
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
    except Exception:
        redis_status = "unhealthy"

    # Get Celery worker count (via Redis)
    worker_count = 0
    queue_depth = {}
    try:
        r = redis.from_url(settings.REDIS_URL)
        # Get active workers
        workers = r.smembers("celery:workers")
        worker_count = len(workers)

        # Get queue depths
        for queue in ["high", "standard", "low"]:
            depth = r.llen(f"celery:queue:{queue}")
            queue_depth[queue] = depth
    except Exception:
        pass

    # Disk usage
    disk = psutil.disk_usage("/")
    disk_usage = {
        "total_gb": round(disk.total / (1024**3), 2),
        "used_gb": round(disk.used / (1024**3), 2),
        "free_gb": round(disk.free / (1024**3), 2),
        "percent": round(disk.used / disk.total * 100, 1),
    }

    return SystemHealthResponse(
        database=db_status,
        redis=redis_status,
        celery_workers=worker_count,
        queue_depth=queue_depth,
        disk_usage=disk_usage,
    )


@router.post("/system/maintenance/cleanup")
async def run_cleanup(
    current_user: User = Depends(require_admin),
) -> dict:
    """Run maintenance cleanup (old exports, temp files, completed chunks)."""
    from geocare.application.use_cases.maintenance import MaintenanceUseCase

    maintenance_uc = container.application.maintenance_use_case
    result = await maintenance_uc.run_cleanup()

    return {
        "message": "Cleanup completed",
        "deleted_files": result.deleted_files,
        "freed_space_mb": result.freed_space_mb,
    }