from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = settings.DATABASE_URL
        if db_url.startswith("sqlite"):
            _engine = create_engine(db_url, connect_args={"check_same_thread": False})
        else:
            try:
                test_engine = create_engine(db_url, pool_pre_ping=True)
                with test_engine.connect():
                    pass
                _engine = test_engine
            except Exception as exc:
                print(f"[database] WARNING: Could not connect to {db_url} ({exc}). Falling back to SQLite.")
                _engine = create_engine("sqlite:///./securedocx.db", connect_args={"check_same_thread": False})
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_factory


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def create_all():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def drop_all():
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)


def SessionLocal():
    """Convenience alias for creating a new database session."""
    return get_session_factory()()
