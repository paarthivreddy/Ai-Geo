"""User entity for GeoCare AI."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class UserRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"


@dataclass
class User:
    """User account entity."""

    id: UUID = field(default_factory=uuid4)
    email: str = ""
    password_hash: str = ""
    full_name: str = ""
    role: UserRole = UserRole.VIEWER
    status: UserStatus = UserStatus.ACTIVE
    salt: str = ""
    last_login_at: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if not self.email:
            raise ValueError("Email is required")
        if not self.password_hash:
            raise ValueError("Password hash is required")
        if not self.salt:
            raise ValueError("Salt is required for patient_id hashing")