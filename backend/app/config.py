"""
Application configuration.
All settings are read from environment variables (or backend/.env).
No configuration values are hardcoded here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """
    Central settings class.  Values are loaded from environment variables
    or from backend/.env (via dotenv_path in model_config).
    """

    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        # backend/.env carries keys for adjacent subsystems (supabase, redis,
        # llm routing) that Settings itself does not declare — ignore them
        # instead of failing startup with extra_forbidden errors.
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    # Accepts both direct (port 5432) and pooler (port 6543) connection strings.
    # Changing connection mode requires only a DATABASE_URL change in .env.
    DATABASE_URL: str

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        """Ensure asyncpg driver scheme is present for async SQLAlchemy engine."""
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    # Stored as a comma-separated string in .env, parsed to a list here.
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # ------------------------------------------------------------------
    # Connection pool
    # ------------------------------------------------------------------
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # ------------------------------------------------------------------
    # Reference Data Cache & Redis
    # ------------------------------------------------------------------
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 300
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_ENABLED: bool = True

    # ------------------------------------------------------------------
    # Google OAuth (configured via environment variables)
    # ------------------------------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:5173/auth/callback"

    # ------------------------------------------------------------------
    # DigiLocker OAuth (configured via environment variables)
    # ------------------------------------------------------------------
    DIGILOCKER_CLIENT_ID: str = ""
    DIGILOCKER_CLIENT_SECRET: str = ""
    DIGILOCKER_REDIRECT_URI: str = "http://localhost:5173/auth/callback"
    DIGILOCKER_BASE_URL: str = "https://digilocker.meripehchaan.gov.in"

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS_ORIGINS as a Python list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings instance.
    The cache is invalidated only on process restart, which is correct
    behaviour for a long-running FastAPI application.
    """
    return Settings()

