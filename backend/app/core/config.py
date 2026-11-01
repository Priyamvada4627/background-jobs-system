import json
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application Information
    APP_NAME: str = "Background Job System"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # PostgreSQL Database Configuration
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "job_system"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    DATABASE_URL: Optional[str] = None
    DATABASE_SYNC_URL: Optional[str] = None

    # Redis Coordination Layer Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # Worker Configuration
    WORKER_CONCURRENCY: int = Field(default=4, ge=1)
    WORKER_POLL_INTERVAL_SECONDS: float = Field(default=1.0, gt=0)
    WORKER_LEASE_TTL_SECONDS: int = Field(default=30, ge=5)
    WORKER_HEARTBEAT_INTERVAL_SECONDS: int = Field(default=10, ge=1)

    # Transactional Outbox Configuration
    OUTBOX_POLL_INTERVAL_SECONDS: float = Field(default=0.5, gt=0)
    OUTBOX_BATCH_SIZE: int = Field(default=100, ge=1)

    # Scheduler Configuration
    SCHEDULER_POLL_INTERVAL_SECONDS: float = Field(default=1.0, gt=0)

    # Lease Reaper Configuration
    REAPER_POLL_INTERVAL_SECONDS: float = Field(default=10.0, gt=0)

    # CORS Origins
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            return json.loads(v)
        return v

    def get_database_url(self) -> str:
        """Returns the async database URL, dynamically constructing or adapting it for asyncpg."""
        if self.DATABASE_URL:
            url_str = self.DATABASE_URL.strip()
            try:
                from sqlalchemy.engine.url import make_url
                parsed = make_url(url_str)
                query = dict(parsed.query)

                # asyncpg does NOT support libpq query params like channel_binding, sslmode, etc.
                sslmode = query.pop("sslmode", None)
                query.pop("channel_binding", None)
                query.pop("target_session_attrs", None)
                query.pop("gssencmode", None)

                # If SSL was requested via sslmode or host is cloud, ensure ssl=require for asyncpg
                if sslmode in ("require", "verify-ca", "verify-full") or "ssl" in query or "neon.tech" in (parsed.host or ""):
                    query["ssl"] = "require"

                drivername = "postgresql+asyncpg"
                return parsed.set(drivername=drivername, query=query).render_as_string(hide_password=False)
            except Exception:
                url = url_str
                if url.startswith("postgres://"):
                    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
                elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
                    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
                url = url.replace("sslmode=", "ssl=")
                import re
                url = re.sub(r"[?&]channel_binding=[^&]+", "", url)
                url = re.sub(r"[?&]target_session_attrs=[^&]+", "", url)
                return url
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def get_database_sync_url(self) -> str:
        """Returns the sync database URL (for Alembic migrations), dynamically constructing or adapting for psycopg2."""
        raw_url = self.DATABASE_SYNC_URL or self.DATABASE_URL
        if raw_url:
            url_str = raw_url.strip()
            try:
                from sqlalchemy.engine.url import make_url
                parsed = make_url(url_str)
                query = dict(parsed.query)

                # For psycopg2 (Alembic), ensure sslmode=require
                if "ssl" in query and "sslmode" not in query:
                    ssl_val = query.pop("ssl")
                    query["sslmode"] = ssl_val if ssl_val in ("require", "verify-ca", "verify-full") else "require"
                elif "sslmode" not in query and ("neon.tech" in (parsed.host or "") or "render.com" in (parsed.host or "")):
                    query["sslmode"] = "require"

                drivername = "postgresql+psycopg2"
                return parsed.set(drivername=drivername, query=query).render_as_string(hide_password=False)
            except Exception:
                url = url_str
                if url.startswith("postgres://"):
                    url = url.replace("postgres://", "postgresql+psycopg2://", 1)
                elif url.startswith("postgresql+asyncpg://"):
                    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
                elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg2://"):
                    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
                return url
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def get_redis_url(self) -> str:
        """Returns the Redis connection URL, auto-upgrading to rediss:// if Upstash or TLS is detected."""
        if self.REDIS_URL:
            url = self.REDIS_URL.strip()
            # If user copied Upstash endpoint with redis:// instead of rediss://
            if "upstash.io" in url and url.startswith("redis://"):
                url = url.replace("redis://", "rediss://", 1)
            return url
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()
