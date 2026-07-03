import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# 1. Import your SQLModel and Settings
from sqlmodel import SQLModel
from src.config import get_settings
from src.db.models import * # Import ALL your models here so Alembic "sees" them

# 2. Get Config
config = context.config
settings = get_settings()

# 3. Setup Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. Set Metadata
target_metadata = SQLModel.metadata

# 5. Database URL comes from src.config (environment variable).
# Avoid config.set_main_option — ConfigParser treats % in passwords as interpolation.


def get_database_url() -> str:
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    url = settings.database.url
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        for param in ("prepared_statements", "prepared_statement_cache_size", "sslmode"):
            params.pop(param, None)
        return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
    except Exception:
        return url


def include_object(object, name, type_, reflected, compare_to):
    """Exclude procrastinate tables from Alembic autogenerate.

    Procrastinate creates its own tables directly in the database,
    but they're not in SQLModel.metadata. Without this filter,
    Alembic would auto-generate op.drop_table() for them every migration.
    """
    if type_ == "table" and name and name.startswith("procrastinate_"):
        return False
    if type_ == "index" and name and "procrastinate" in name:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    
    # Get the database URL
    db_url = get_database_url()
    
    # Configure connect_args for Supabase/pgbouncer compatibility
    connect_args = {"statement_cache_size": 0}
    if "supabase" in db_url:
        connect_args["ssl"] = "require"
    if "supabase" in db_url or ":6543" in db_url:
        connect_args["statement_cache_size"] = 0
    
    # Use create_async_engine directly to support connect_args
   
    connectable = create_async_engine(
        db_url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())