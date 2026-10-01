from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models added by feature modules."""


class Database:
    def __init__(self, url: str | URL):
        options: dict[str, object] = {"pool_pre_ping": True}
        if str(url) == "sqlite://":
            options.update(
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        elif str(url).startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}

        self.engine: Engine = create_engine(url, **options)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )

    def dispose(self) -> None:
        self.engine.dispose()


def get_db(request: Request) -> Generator[Session, None, None]:
    """Provide one database session per request and always close it afterward."""
    database: Database = request.app.state.database
    with database.session_factory() as session:
        yield session
