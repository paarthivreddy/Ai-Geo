"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from geocare.config.container import container
from geocare.config.logging import setup_logging, get_logger
from geocare.config.database import init_db, close_db
from geocare.presentation.api.routes import (
    auth,
    files,
    jobs,
    dashboard,
    exports,
    reports,
    admin,
)
from geocare.presentation.ws import progress


# Setup logging
setup_logging()
logger = get_logger("geocare.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    logger.info("Starting GeoCare AI application")

    # Initialize database
    await init_db()

    # Initialize geography engine (loads indexes)
    logger.info("Initializing geography engine...")
    # This would be triggered on first use or via admin endpoint

    logger.info("Application startup complete")
    yield

    # Shutdown
    logger.info("Shutting down GeoCare AI application")
    await close_db()
    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="GeoCare AI",
    description="India Patient Address Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if container.config.DEBUG() else None,
    redoc_url="/redoc" if container.config.DEBUG() else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=container.config.CORS_ORIGINS(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
if container.config.PROMETHEUS_METRICS_ENABLED():
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(exports.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

# Include WebSocket router
app.include_router(progress.router, prefix="/api/v1/ws")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Health check endpoint
@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "service": "geocare-ai",
        "version": "1.0.0",
    }


@app.get("/health/ready")
async def readiness_check() -> dict:
    """Readiness check - verifies database connectivity."""
    from geocare.config.database import engine
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "database": "disconnected", "error": str(e)},
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "geocare.main:app",
        host="0.0.0.0",
        port=8000,
        reload=container.config.DEBUG(),
        log_config=None,  # Use structlog
    )