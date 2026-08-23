"""
app/data/database.py
─────────────────────
SQLAlchemy engine + session factory.
Provides both sync (for scripts/tests) and async (for FastAPI) engines.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# Sync engine — used by ingest scripts, tests, and repository functions
sync_engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
    echo=settings.app_env == "development",
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Sync session context manager for scripts and dependency injection."""
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a sync session."""
    with get_db() as session:
        yield session
