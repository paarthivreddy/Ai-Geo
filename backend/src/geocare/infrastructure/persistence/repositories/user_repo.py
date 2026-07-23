"""User repository implementation."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.domain.entities.user import User, UserRole, UserStatus
from geocare.domain.ports.repositories import UserRepository
from geocare.infrastructure.persistence.models import UserModel
from geocare.config.database import async_session_factory


class UserRepositoryImpl(UserRepository):
    """SQLAlchemy implementation of UserRepository."""

    def __init__(self, session_factory=async_session_factory):
        self.session_factory = session_factory

    async def create(self, user: User) -> User:
        async with self.session_factory() as session:
            model = UserModel(
                id=str(user.id),
                email=user.email,
                password_hash=user.password_hash,
                full_name=user.full_name,
                role=user.role.value,
                status=user.status.value,
                salt=user.salt,
                last_login_at=user.last_login_at,
                failed_login_attempts=user.failed_login_attempts,
                locked_until=user.locked_until,
            )
            session.add(model)
            await session.flush()
            await session.commit()
            return user

    async def get(self, user_id: UUID) -> Optional[User]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == str(user_id))
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._to_entity(model)

    async def get_by_email(self, email: str) -> Optional[User]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.email == email)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._to_entity(model)

    async def update(self, user: User) -> User:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == str(user.id))
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(f"User {user.id} not found")

            model.email = user.email
            model.password_hash = user.password_hash
            model.full_name = user.full_name
            model.role = user.role.value
            model.status = user.status.value
            model.salt = user.salt
            model.last_login_at = user.last_login_at
            model.failed_login_attempts = user.failed_login_attempts
            model.locked_until = user.locked_until
            model.updated_at = user.updated_at

            await session.flush()
            await session.commit()
            return user

    async def list(
        self,
        limit: int = 50,
        offset: int = 0,
        role: Optional[str] = None,
    ) -> list[User]:
        async with self.session_factory() as session:
            query = select(UserModel).order_by(UserModel.created_at.desc()).limit(limit).offset(offset)
            if role:
                query = query.where(UserModel.role == role)
            result = await session.execute(query)
            return [self._to_entity(m) for m in result.scalars().all()]

    async def count(self, role: Optional[str] = None) -> int:
        async with self.session_factory() as session:
            query = select(func.count(UserModel.id))
            if role:
                query = query.where(UserModel.role == role)
            result = await session.execute(query)
            return result.scalar_one()

    def _to_entity(self, model: UserModel) -> User:
        return User(
            id=UUID(model.id),
            email=model.email,
            password_hash=model.password_hash,
            full_name=model.full_name,
            role=UserRole(model.role),
            status=UserStatus(model.status),
            salt=model.salt,
            last_login_at=model.last_login_at,
            failed_login_attempts=model.failed_login_attempts,
            locked_until=model.locked_until,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
