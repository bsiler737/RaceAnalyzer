"""SQLAlchemy engine and session factory."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from raceanalyzer.db.models import Base

DEFAULT_DB_PATH = Path("data/raceanalyzer.db")


def get_engine(db_path: Path = DEFAULT_DB_PATH):
    """Create a SQLAlchemy engine with WAL mode for concurrent writes."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def get_session(db_path: Path = DEFAULT_DB_PATH) -> Session:
    """Create a new database session."""
    engine = get_engine(db_path)
    return sessionmaker(bind=engine)()


def init_db(db_path: Path = DEFAULT_DB_PATH):
    """Create all tables. Idempotent."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine
