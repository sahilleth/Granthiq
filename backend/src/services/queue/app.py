import procrastinate
from loguru import logger
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from src.config import get_settings

settings = get_settings()


def get_procrastinate_config():
    """
    Generate robust configuration for Procrastinate PsycopgConnector.
    Puts 'sslmode' into the DSN string where it belongs.
    """
    original_url = settings.database.url

    # CRITICAL: Check if DATABASE_URL is set
    if not original_url:
        error_msg = (
            " DATABASE_URL environment variable is not set!\n"
            "   Set it in your .env file or Railway/Render dashboard:\n"
            "   DATABASE_URL=postgresql://user:pass@host:5432/dbname"
        )
        logger.error(error_msg)
        raise ValueError("DATABASE_URL is required for Procrastinate task queue")

    # 1. Clean Protocol (Procrastinate uses standard postgresql://)
    clean_url = original_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )

    # 2. Force Port 5432 (Session Mode) if using port 6543
    # Note: LISTEN/NOTIFY is disabled in worker.py (listen_notify=False) to avoid Windows/psycopg issues
    if ":6543" in clean_url:
        clean_url = clean_url.replace(":6543", ":5432")
        logger.info("Forced port 5432 for Procrastinate")

    try:
        # 3. Parse URL
        parsed = urlparse(clean_url)
        query_params = parse_qs(parsed.query)

        # 4. Fix SSL Parameters for Psycopg
        # Remove 'ssl' (used by asyncpg)
        if "ssl" in query_params:
            del query_params["ssl"]

        # Remove asyncpg-only parameters that psycopg doesn't understand
        for asyncpg_param in ["prepared_statements", "statement_cache_size"]:
            if asyncpg_param in query_params:
                del query_params[asyncpg_param]
                logger.debug(
                    f"Removed asyncpg-only param '{asyncpg_param}' from Procrastinate DSN"
                )

        # Add 'sslmode=require' (used by psycopg/libpq)
        # 'require' is the standard for cloud DBs like Supabase
        query_params["sslmode"] = ["require"]

        # Add TCP keepalive settings to prevent Supabase idle disconnects
        # These are libpq connection parameters (go in DSN, not pool kwargs)
        query_params["keepalives"] = ["1"]  # Enable TCP keepalive
        query_params["keepalives_idle"] = ["30"]  # Send keepalive after 30s idle
        query_params["keepalives_interval"] = ["10"]  # Retry every 10s
        query_params["keepalives_count"] = ["5"]  # Give up after 5 retries

        # 5. Reconstruct URL
        new_query = urlencode(query_params, doseq=True)
        dsn = urlunparse(parsed._replace(query=new_query))

        return {
            "conninfo": dsn,
            # Pass empty dict for kwargs to avoid "NoneType" errors in internal psycopg calls
            # but don't pass invalid args like sslmode here.
            "kwargs": {},
        }

    except Exception as e:
        logger.error("Failed to parse DB URL: {}", e)
        # Fallback to raw string if parsing fails, but try to append sslmode
        fallback_url = clean_url
        if "sslmode" not in fallback_url:
            sep = "&" if "?" in fallback_url else "?"
            fallback_url += f"{sep}sslmode=require"
        return {"conninfo": fallback_url, "kwargs": {}}


# Initialize Procrastinate App
config = get_procrastinate_config()

# Ensure kwargs is always a dict, never None
kwargs = config.get("kwargs") or {}

# Add connection pool configuration to prevent pool exhaustion
# NOTE: Using smaller pool for Procrastinate since the main app also uses connections
# Supabase free tier allows 60 concurrent connections total
# Main app: 20 pool + 25 overflow = 45 connections
# Procrastinate: 2 min + 5 max = 7 connections
# Total: ~52 connections (within 60 limit with 8 connection buffer)
kwargs["min_size"] = 2  # Lower minimum since worker tasks are batched
kwargs["max_size"] = 5  # Reduced to leave headroom for main app pool
kwargs["max_idle"] = 2  # Close idle connections faster
kwargs["timeout"] = 20  # Fail faster if connection not available
kwargs["timeout"] = (
    30  # Connection acquisition timeout (reduced from 60 for faster failure)
)
# Note: TCP keepalive settings are now in the DSN (get_procrastinate_config)

try:
    proc_app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(
            conninfo=config["conninfo"],
            **kwargs,  # Guaranteed to be a dict with pool config
        )
    )
    logger.info(
        f"✓ Procrastinate app initialized (DSN len: {len(config['conninfo'])}, pool: 10-30 connections)"
    )
except Exception as e:
    logger.error("Failed to initialize Procrastinate: {}", e)
    # Create a dummy app that will fail gracefully
    proc_app = None

# Queue names (priority-based)
QUEUE_CRITICAL = "critical"
QUEUE_HIGH = "high"
QUEUE_STANDARD = "standard"

__all__ = ["proc_app", "QUEUE_CRITICAL", "QUEUE_HIGH", "QUEUE_STANDARD"]
