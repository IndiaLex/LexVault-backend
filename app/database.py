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
        _engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
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
