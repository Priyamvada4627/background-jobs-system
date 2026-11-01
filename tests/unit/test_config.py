import pytest
from app.core.config import Settings


def test_default_settings():
    s = Settings(_env_file=None)
    assert s.APP_NAME == "Background Job System"
    assert s.POSTGRES_PORT == 5432
    assert s.REDIS_PORT == 6379
    assert s.WORKER_CONCURRENCY == 4
    assert "postgresql+asyncpg://" in s.get_database_url()
    assert "postgresql+psycopg2://" in s.get_database_sync_url()
    assert "redis://localhost:6379/0" == s.get_redis_url()


def test_custom_database_url_override():
    custom_url = "postgresql+asyncpg://user:pass@remote-host:5433/custom_db"
    s = Settings(DATABASE_URL=custom_url)
    assert s.get_database_url() == custom_url


def test_custom_redis_url_override():
    custom_url = "redis://:secret@remote-redis:6380/2"
    s = Settings(REDIS_URL=custom_url)
    assert s.get_redis_url() == custom_url


def test_cors_origin_parsing():
    # Test comma-separated string
    s1 = Settings(CORS_ORIGINS="http://localhost:3000,http://example.com")
    assert s1.CORS_ORIGINS == ["http://localhost:3000", "http://example.com"]

    # Test JSON list string
    s2 = Settings(CORS_ORIGINS='["http://localhost:5173", "http://api.local"]')
    assert s2.CORS_ORIGINS == ["http://localhost:5173", "http://api.local"]

    # Test direct python list
    s3 = Settings(CORS_ORIGINS=["http://test.com"])
    assert s3.CORS_ORIGINS == ["http://test.com"]
