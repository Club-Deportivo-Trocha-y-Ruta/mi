from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.models import Base

config = context.config
# A programmatic caller (tests/test_audit_mysql.py) pins its `_test` database
# through `Config.attributes`; the CLI and entrypoint.sh keep using settings.
_raw_sqlalchemy_url = config.attributes.get("sqlalchemy.url") or settings.database_url_sync
# ConfigParser interpola "%" por defecto; escapamos antes de guardarlo porque
# la contraseña de MySQL percent-encoded puede contener secuencias %XX.
config.set_main_option("sqlalchemy.url", _raw_sqlalchemy_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "format"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
