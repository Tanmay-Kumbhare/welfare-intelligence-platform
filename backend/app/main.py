"""
FastAPI application entry point.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import get_settings
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context: initialize and cleanup resources."""
    # 1. Startup: initialize Redis connection pool (best-effort)
    try:
        health = await cache_service.health()
        if health.get("status") == "connected":
            logger.info("Redis cache connected at %s", cache_service.redis_url)
        else:
            logger.warning(
                "Redis unavailable on startup (%s). App will bypass cache and query PostgreSQL directly.",
                health.get("reason", "unknown"),
            )
    except Exception as exc:
        logger.warning("Redis initialization error: %s (bypassing cache)", exc)

    yield

    # 2. Shutdown: cleanly close Redis connection pool
    try:
        await cache_service.close()
        logger.info("Redis connection pool closed cleanly.")
    except Exception as exc:
        logger.warning("Error closing Redis connection pool: %s", exc)


app = FastAPI(
    title="Welfare Intelligence Platform API",
    description="API for evaluating citizen eligibility for welfare schemes.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 router
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint with Redis and database diagnostics."""
    redis_health = await cache_service.health()
    return {
        "status": "ok",
        "cache": {
            "type": "redis",
            "redis_status": redis_health.get("status"),
            "redis_url": redis_health.get("url"),
            "hits": redis_health.get("hits", 0),
            "misses": redis_health.get("misses", 0),
        },
    }