from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from Application.Configurations import settings
from .Models import Base, User, UserRole

# Ensure all SQLAlchemy models are registered
import Application.Activity.Models  # noqa: F401
import Application.Clients.Models  # noqa: F401
import Application.Engagements.Models  # noqa: F401
import Application.Finance.Models  # noqa: F401
import Application.Projects.Models  # noqa: F401
import Application.Tasks.Models  # noqa: F401
import Application.Settings.Models  # noqa: F401

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class UserRepository:
    def get_by_id(self, session: Session, user_id: int) -> User | None:
        return session.get(User, user_id)

    def get_by_email(self, session: Session, email: str) -> User | None:
        return session.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))

    def list(
        self, session: Session, query: str = "", role: str = "", status: str = ""
    ) -> list[User]:
        statement = select(User).order_by(User.name)
        if query:
            term = f"%{query.strip().lower()}%"
            statement = statement.where(
                func.lower(User.name).like(term) | func.lower(User.email).like(term)
            )
        if role in {item.value for item in UserRole}:
            statement = statement.where(User.role == role)
        if status == "active":
            statement = statement.where(User.is_active.is_(True))
        elif status == "inactive":
            statement = statement.where(User.is_active.is_(False))
        return list(session.scalars(statement))

    def count_active_developers(self, session: Session) -> int:
        return int(
            session.scalar(
                select(func.count(User.id)).where(
                    User.role == UserRole.DEVELOPER.value, User.is_active.is_(True)
                )
            )
            or 0
        )

    def add(self, session: Session, user: User) -> User:
        session.add(user)
        session.flush()
        return user


def initialize_database() -> None:
    """Run versioned migrations. Kept as the public startup/CLI entry point."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(settings_project_dir() / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def settings_project_dir():
    from Application.Configurations import PROJECT_DIR
    return PROJECT_DIR
