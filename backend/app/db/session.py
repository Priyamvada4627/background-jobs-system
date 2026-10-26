import time
from typing import AsyncGenerator, Dict, Any, Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine
from sqlalchemy import text
from app.core.config import settings

# Engine and sessionmaker placeholders for lazy initialization or lifecycle management
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_url = settings.get_database_url()
        connect_args = {}
        if "postgresql" in db_url:
            connect_args["timeout"] = 3.0

        _engine = create_async_engine(
            db_url,
            echo=settings.DEBUG and settings.ENVIRONMENT == "development",
            future=True,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            connect_args=connect_args,
        )
    return _engine



def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields a database session for route requests."""
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_db_health(timeout: float = 3.0) -> Dict[str, Any]:
    """Checks database connectivity by issuing a lightweight SELECT 1 query."""
    import asyncio
    engine = get_engine()
    start_time = time.perf_counter()
    try:
        async def _query():
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_query(), timeout=timeout)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(exc),
        }



async def close_db_connection() -> None:
    """Disposes of the database engine on application shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
