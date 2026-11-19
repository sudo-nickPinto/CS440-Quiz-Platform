from collections.abc import Callable, Generator
from typing import Any, TypeVar

from fastapi import FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.concurrency import run_in_threadpool

T = TypeVar("T")


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


async def run_in_db_session(
    app: FastAPI,
    fn: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Run a sync service call in the threadpool with its own short-lived session.

    Shared by the WebSocket hubs (LIVE_PROTOCOL.md §8.1): one fresh session per
    call, never one held for the life of a socket.
    """

    def call() -> T:
        with app.state.database.session_factory() as db:
            return fn(db, *args, **kwargs)

    return await run_in_threadpool(call)
