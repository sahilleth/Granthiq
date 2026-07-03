from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from sqlmodel import SQLModel
from loguru import logger
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from src.config import get_settings
from src.constants import (
    DATABASE_POOL_SIZE,
    DATABASE_MAX_OVERFLOW,
    DATABASE_POOL_TIMEOUT,
    DATABASE_POOL_RECYCLE,
)


settings = get_settings()


connect_args = {}

# CRITICAL: Check if DATABASE_URL is set
if not settings.database.url:
    import os

    # Debug: Check what env vars are actually available
    db_url_raw = os.getenv("DATABASE_URL")
    postgres_url = os.getenv("POSTGRES_URL")
    database_public = os.getenv("DATABASE_PUBLIC_URL")

    error_msg = (
        " DATABASE_URL environment variable is not set!\n"
        "   This is REQUIRED for the application to start.\n"
        "   \n"
        f"   DEBUG: DATABASE_URL raw = {db_url_raw[:30] + '...' if db_url_raw else 'None'}\n"
        f"   DEBUG: POSTGRES_URL = {postgres_url[:30] + '...' if postgres_url else 'None'}\n"
        f"   DEBUG: DATABASE_PUBLIC_URL = {database_public[:30] + '...' if database_public else 'None'}\n"
        "   \n"
        "   In Railway:\n"
        "   1. If using Railway PostgreSQL: Add reference variable DATABASE_URL=${{Postgres.DATABASE_URL}}\n"
        "   2. Or go to your service → Variables tab → 'Raw Editor'\n"
        "   3. Add: DATABASE_URL=postgresql://user:pass@host:5432/dbname\n"
        "   4. Click 'Update Variables'"
    )
    logger.error(error_msg)
    raise ValueError("DATABASE_URL is required")


def _clean_database_url(url: str) -> str:
    """
    Strip asyncpg-only query parameters from the DATABASE_URL.
    'prepared_statements' is NOT a valid asyncpg connect() kwarg —
    it only works when passed via connect_args['statement_cache_size'].
    Leaving it in the URL causes psycopg (Procrastinate) and even
    asyncpg to reject the connection string.
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        invalid_params = ["prepared_statements", "prepared_statement_cache_size", "sslmode"]
        removed = []
        for p in invalid_params:
            if p in params:
                del params[p]
                removed.append(p)
        if removed:
            new_query = urlencode(params, doseq=True)
            url = urlunparse(parsed._replace(query=new_query))
            logger.info(f"Stripped invalid URL params from DATABASE_URL: {removed}")
        return url
    except Exception:
        return url


# Clean the URL before using it
db_url = _clean_database_url(settings.database.url)

# CRITICAL: Check if using pgbouncer BEFORE any port modifications
# This determines whether to use NullPool (for pgbouncer) or connection pooling
is_pgbouncer = ":6543" in db_url or "pooler.supabase.com" in db_url

# Force direct connection (port 5432) instead of pgbouncer (port 6543)
# to avoid prepared statement issues with asyncpg
if ":6543" in db_url:
    db_url = db_url.replace(":6543", ":5432")
    logger.info(
        "Forced port 5432 (direct PostgreSQL) instead of 6543 (pgbouncer) for asyncpg. "
        "Using NullPool to avoid connection reuse issues with pgbouncer."
    )

if "sqlite" in db_url:
    connect_args["check_same_thread"] = False

else:
    # CRITICAL: Always disable prepared statement caching for PostgreSQL
    # Supabase/Coolify use pgbouncer in transaction mode which doesn't support
    # prepared statements. This must be set regardless of how DATABASE_URL is formatted.
    # 'statement_cache_size' is the ONLY correct asyncpg connect_args key for this.
    connect_args["statement_cache_size"] = 0

    # Enable SSL if connecting to Supabase or if ssl=require is in URL
    if "ssl=require" in db_url or "supabase" in db_url:
        connect_args["ssl"] = "require"


# Build engine kwargs conditionally based on pool type
engine_kwargs = {
    "url": db_url,
    "echo": settings.database.echo,
    "connect_args": connect_args,
    "future": True,
}

# Use NullPool for pgbouncer to avoid prepared statement and connection reuse issues
# Supabase/Coolify use pgbouncer in transaction mode which doesn't support
# prepared statements properly. NullPool creates new connections for each request,
# letting pgbouncer handle the actual connection pooling.
if is_pgbouncer:
    # For pgbouncer, use NullPool to avoid connection reuse issues
    engine_kwargs["poolclass"] = NullPool
    logger.info("Using NullPool for pgbouncer connection")
else:
    # Use AsyncAdaptedQueuePool for direct connections
    engine_kwargs["poolclass"] = AsyncAdaptedQueuePool
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = DATABASE_POOL_SIZE
    engine_kwargs["max_overflow"] = DATABASE_MAX_OVERFLOW
    engine_kwargs["pool_timeout"] = DATABASE_POOL_TIMEOUT
    engine_kwargs["pool_recycle"] = DATABASE_POOL_RECYCLE
    logger.info(
        f"Using AsyncAdaptedQueuePool with "
        f"pool_size={DATABASE_POOL_SIZE}, "
        f"max_overflow={DATABASE_MAX_OVERFLOW}, "
        f"statement_cache_size={connect_args.get('statement_cache_size', 'default')}"
    )

engine = create_async_engine(**engine_kwargs)


# Add connection pool monitoring for debugging
from sqlalchemy import event
import time

# Track connection checkouts to detect leaks
_connection_checkout_times = {}


@event.listens_for(engine.sync_engine, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log when connection is checked out from pool."""
    if hasattr(engine.pool, "size"):
        pool = engine.pool
        checkout_time = time.time()
        _connection_checkout_times[id(connection_record)] = checkout_time
        
        # Log at INFO level if pool is getting saturated
        checked_out = pool.checkedout()
        pool_size = pool.size()
        saturation = (checked_out / pool_size) * 100 if pool_size > 0 else 0
        
        if saturation > 80:
            logger.warning(
                f"DB Pool saturation HIGH ({saturation:.0f}%) - "
                f"checked_out: {checked_out}/{pool_size}, overflow: {pool.overflow()}"
            )
        else:
            logger.debug(
                f"DB Connection checked out - Pool: {pool.checkedin()}/{pool.size()} available, "
                f"Overflow: {pool.overflow()}/{pool._max_overflow}"
            )


@event.listens_for(engine.sync_engine, "checkin")
def on_checkin(dbapi_conn, connection_record):
    """Log when connection is returned to pool."""
    if hasattr(engine.pool, "size"):
        pool = engine.pool
        
        # Calculate how long the connection was checked out
        checkout_time = _connection_checkout_times.pop(id(connection_record), None)
        if checkout_time:
            duration = time.time() - checkout_time
            if duration > 30:  # Warn if connection held for more than 30 seconds
                logger.warning(
                    f"DB Connection held for {duration:.1f}s - possible leak detected! "
                    f"Connection should be released sooner."
                )
        
        logger.debug(
            f"DB Connection checked in - Pool: {pool.checkedin()}/{pool.size()} available"
        )


async_session_factory = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_session() -> AsyncSession:
    """
    Dependency to provide a database session.
    """
    async with async_session_factory() as session:
        yield session


async def init_db():
    """
    Initialize the database (Local/Dev only).
    """
    if "sqlite" in settings.database.url:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)


def get_pool_status() -> dict:
    """
    Get current connection pool status for monitoring.
    Returns dict with pool statistics.
    """
    if hasattr(engine.pool, "size"):
        pool = engine.pool
        checked_out = pool.checkedout()
        pool_size = pool.size()
        total = pool.checkedin() + checked_out
        max_total = pool_size + pool._max_overflow
        
        # Calculate saturation percentage
        saturation = (checked_out / pool_size * 100) if pool_size > 0 else 0
        capacity_used = (total / max_total * 100) if max_total > 0 else 0
        
        status = {
            "pool_type": engine.pool.__class__.__name__,
            "pool_size": pool_size,
            "checked_in": pool.checkedin(),
            "checked_out": checked_out,
            "overflow": pool.overflow(),
            "max_overflow": pool._max_overflow,
            "total_connections": total,
            "max_capacity": max_total,
            "saturation_pct": round(saturation, 1),
            "capacity_used_pct": round(capacity_used, 1),
            "status": "healthy" if saturation < 70 else "warning" if saturation < 90 else "critical",
            "outstanding_checkouts": len(_connection_checkout_times),
        }
        
        # Add warning if leak detected
        if len(_connection_checkout_times) > pool_size:
            status["leak_warning"] = f"Possible connection leak: {len(_connection_checkout_times)} tracked checkouts > pool size"
        
        return status
    else:
        return {
            "pool_type": engine.pool.__class__.__name__,
            "note": "Pool status not available for NullPool",
        }
