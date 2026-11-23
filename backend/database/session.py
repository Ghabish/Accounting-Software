"""Engine and session management."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings

_engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False, future=True)


def make_engine(url: str, echo: bool = False) -> Engine:
    kwargs: dict = {"echo": echo, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _rec):  # pragma: no cover - sqlite only
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = make_engine(s.database_url, s.sql_echo)
        SessionLocal.configure(bind=_engine)
    return _engine


def set_engine(engine: Engine) -> None:
    """Used by tests to bind the session factory to a specific engine."""
    global _engine
    _engine = engine
    SessionLocal.configure(bind=engine)


def get_db() -> Iterator[Session]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
