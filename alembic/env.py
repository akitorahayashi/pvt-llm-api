import logging
import os
from pydantic import ValidationError

from sqlalchemy import create_engine, pool

import src.db.models  # noqa: F401
from alembic import context
from src.db.database import Base
from src.config.settings import Settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Set up logging if it's not already configured
if not logging.getLogger().handlers:
    logging.basicConfig(level="INFO")

# Set alembic logger level specifically
logging.getLogger("alembic").setLevel(os.getenv("ALEMBIC_LOG_LEVEL", "INFO"))


def _get_settings() -> Settings:
    """Load settings and validate DATABASE_URL."""
    try:
        settings = Settings()
        if not settings.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL が未設定です。Alembic を実行する前に環境変数/.env を準備してください。"
            )
        return settings
    except (ValidationError, ValueError) as e:
        # Re-raise with a more user-friendly message
        raise ValueError(str(e)) from e


# Use the application's settings to configure the database URL.
settings = _get_settings()


# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # Add batch mode support for SQLite
        is_sqlite = connection.dialect.name == "sqlite"
        configure_opts = {
            "connection": connection,
            "target_metadata": target_metadata,
            "compare_type": True,
            "compare_server_default": True,
        }
        if is_sqlite:
            configure_opts["render_as_batch"] = True

        context.configure(**configure_opts)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
