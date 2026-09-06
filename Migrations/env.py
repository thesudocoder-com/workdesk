from alembic import context
from sqlalchemy import engine_from_config, pool

from Application.Users.Models import Base
import os
import Application.Activity.Models
import Application.Clients.Models
import Application.Engagements.Models
import Application.Finance.Models
import Application.Projects.Models
import Application.Settings.Models
import Application.Tasks.Models

config = context.config
if os.getenv("WORKDESK_DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["WORKDESK_DATABASE_URL"].replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
