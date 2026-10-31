from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def create_database_engine(url: str):
    options = {"pool_pre_ping": True}
    if url.startswith(("postgresql:", "postgresql+")):
        options["connect_args"] = {"connect_timeout": settings.database_connect_timeout_seconds}
    return create_engine(url, **options)


engine = create_database_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
