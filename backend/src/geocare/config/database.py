"""Database configuration and session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from geocare.config.settings import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# Primary database engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# OSM database engine
osm_engine: AsyncEngine = create_async_engine(
    settings.OSM_DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

osm_session_factory = async_sessionmaker(
    osm_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for the primary database."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_osm_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for the OSM database."""
    async with osm_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database connections and verify connectivity."""
    # Test primary DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Test OSM DB (optional - skip if unavailable)
    try:
        async with osm_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        import logging
        logging.getLogger("geocare.db").warning(f"OSM database unavailable, continuing without it: {e}")


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    await osm_engine.dispose()


# Event listeners for query logging (debug only)
if settings.DEBUG:
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(
            __import__("time").time()
        )

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total = __import__("time").time() - conn.info["query_start_time"].pop(-1)
        if total > 1.0:  # Log slow queries > 1s
            from geocare.config.logging import get_logger
            logger = get_logger("geocare.db.slow")
            logger.warning(
                "slow_query",
                duration_ms=total * 1000,
                statement=statement[:500],
            )