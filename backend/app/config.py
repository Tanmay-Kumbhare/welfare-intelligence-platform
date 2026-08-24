"""
Application configuration.
All settings are read from environment variables (or backend/.env).
No configuration values are hardcoded here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings class.  Values are loaded from environment variables
    or from backend/.env (via dotenv_path in model_config).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    # Accepts both direct (port 5432) and pooler (port 6543) connection strings.
    # Changing connection mode requires only a DATABASE_URL change in .env.
    DATABASE_URL: str

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
