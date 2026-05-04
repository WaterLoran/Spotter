import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import SQLEYE_DB_PATH


SQLALCHEMY_DATABASE_URL = f"sqlite:///{SQLEYE_DB_PATH}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def migrate_sessions_allow_multiple_per_system() -> None:
    """SQLite: drop implicit UNIQUE(system_id) on sessions so multiple connections per system are allowed.

    Preserves row ids so QueryTask / FieldSearchTask / QueryHistory FKs stay valid.
    """
    path = Path(SQLEYE_DB_PATH)
    if not path.exists():
        return
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        if not cur.fetchone():
            return
        cur.execute("PRAGMA index_list('sessions')")
        rows = cur.fetchall()
        # (seq, name, unique, origin, partial)
        has_auto_unique = any(
            int(r[2]) == 1 and str(r[1]).startswith("sqlite_autoindex_sessions") for r in rows
        )
        if not has_auto_unique:
            cur.execute("CREATE INDEX IF NOT EXISTS ix_sessions_system_id ON sessions (system_id)")
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sessions_system_db_type_name "
                "ON sessions (system_id, db_type, name)"
            )
            conn.commit()
            return

        cur.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE sessions_new (
                id INTEGER NOT NULL PRIMARY KEY,
                system_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                db_type VARCHAR(20) NOT NULL,
                host VARCHAR(255) NOT NULL,
                port INTEGER NOT NULL,
                username VARCHAR(100) NOT NULL,
                password TEXT NOT NULL,
                database VARCHAR(100) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            );
            INSERT INTO sessions_new (
                id, system_id, name, db_type, host, port, username, password, database, created_at, updated_at
            )
            SELECT id, system_id, name, db_type, host, port, username, password, database, created_at, updated_at
            FROM sessions;
            DROP TABLE sessions;
            ALTER TABLE sessions_new RENAME TO sessions;
            CREATE INDEX IF NOT EXISTS ix_sessions_system_id ON sessions (system_id);
            CREATE UNIQUE INDEX IF NOT EXISTS uq_sessions_system_db_type_name
                ON sessions (system_id, db_type, name);
            PRAGMA foreign_keys=ON;
            """
        )
        conn.commit()
    finally:
        conn.close()


migrate_sessions_allow_multiple_per_system()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
