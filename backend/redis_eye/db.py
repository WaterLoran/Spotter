from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import REDIS_DB_PATH

SQLALCHEMY_DATABASE_URL = f"sqlite:///{REDIS_DB_PATH}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
