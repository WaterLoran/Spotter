import sqlite3

import psycopg2
import pymysql


def _coerce_port(db_type: str, port) -> int:
    if db_type == "sqlite":
        return 0
    if port is None or port == "":
        return 5432 if db_type == "pgsql" else 3306
    try:
        return int(port)
    except (TypeError, ValueError) as e:
        raise ValueError("端口必须是有效数字") from e


def connect_db(session_obj):
    db_type = (getattr(session_obj, "db_type", None) or "mysql")
    if isinstance(db_type, str):
        db_type = db_type.strip().lower()
    else:
        db_type = "mysql"

    port = _coerce_port(db_type, getattr(session_obj, "port", None))
    host = getattr(session_obj, "host", None) or "127.0.0.1"
    user = getattr(session_obj, "username", None) or ""
    password = getattr(session_obj, "password", None) or ""
    database = getattr(session_obj, "database", None) or ""

    if db_type == "sqlite":
        path = (database or ":memory:").strip() or ":memory:"
        return sqlite3.connect(path, timeout=10)

    if db_type == "mysql":
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
        )

    if db_type in ("pgsql", "postgres", "postgresql"):
        return psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database,
            connect_timeout=10,
        )

    raise ValueError(f"不支持的数据库类型: {db_type!r}，请使用 mysql、pgsql 或 sqlite")
