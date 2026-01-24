from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from contextlib import asynccontextmanager
import logging
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    connect_args={
        "timeout": 30,
        "command_timeout": 60,
        "server_settings": {
            "application_name": "fastapi_app"
        },
        "statement_cache_size": 0,
    },
    echo=False,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


from typing import AsyncGenerator

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting database sessions.
    Handles connection errors gracefully.
    """
    session = async_session_maker()
    try:
        yield session
    except Exception as e:
        logger.error(f"Session error: {e}")
        await safe_rollback(session)
        raise
    finally:
        await safe_close(session)


async def safe_rollback(session: AsyncSession):
    """Safely rollback a session, ignoring connection errors."""
    try:
        await session.rollback()
    except Exception as e:
        logger.debug(f"Rollback failed (connection may be closed): {e}")


async def safe_close(session: AsyncSession):
    """Safely close a session, ignoring connection errors."""
    try:
        await session.close()
    except Exception as e:
        logger.debug(f"Session close failed (connection may be closed): {e}")


async def check_db_connection() -> bool:
    """Verify database connectivity."""
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def warmup_db_connection():
    """Warm up database connection on startup."""
    for attempt in range(3):
        if await check_db_connection():
            logger.info("Database connection established successfully")
            return True
        logger.warning(f"Database warmup attempt {attempt + 1} failed, retrying...")
        await asyncio.sleep(2)
    logger.warning("Could not establish initial database connection")
    return False


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan context manager."""
    logger.info("Starting up application...")
    await warmup_db_connection()
    yield
    logger.info("Shutting down application...")
    await engine.dispose()