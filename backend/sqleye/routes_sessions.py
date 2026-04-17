from flask import Blueprint, g, jsonify, request

from sqleye.db import Base, SessionLocal, engine
from sqleye.models import FieldSearchTask, QueryHistory, QueryTask, Session  # noqa: F401
from sqleye.services.db_connector import connect_db


sql_sessions_bp = Blueprint("sql_sessions", __name__)
Base.metadata.create_all(bind=engine)


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


def _session_from_payload(payload: dict):
    class C:
        pass

    c = C()
    p = payload or {}
    c.db_type = p.get("db_type")
    c.host = p.get("host")
    c.port = p.get("port")
    c.username = p.get("username")
    c.password = p.get("password")
    c.database = p.get("database")
    return c


def _test_connection_failed(message: str):
    return jsonify({"success": False, "error": message, "message": "", "data": {"connected": False}})


def _friendly_connect_error(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 400:
        text = text[:400] + "…"
    return f"无法连接数据库: {text}"


@sql_sessions_bp.get("/sessions")
def get_session():
    db = SessionLocal()
    try:
        row = db.query(Session).filter(Session.system_id == int(g.system_id)).first()
        return ok(
            {
                "id": row.id,
                "name": row.name,
                "db_type": row.db_type,
                "host": row.host,
                "port": row.port,
                "username": row.username,
                "password": row.password,
                "database": row.database,
            }
            if row
            else None
        )
    finally:
        db.close()


@sql_sessions_bp.post("/sessions")
def save_session():
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.query(Session).filter(Session.system_id == int(g.system_id)).first()
        if not row:
            row = Session(system_id=int(g.system_id))
            db.add(row)
        for k in ["name", "db_type", "host", "port", "username", "password", "database"]:
            setattr(row, k, payload.get(k))
        db.commit()
        return ok({"id": row.id})
    finally:
        db.close()


@sql_sessions_bp.post("/sessions/test")
def test_session():
    payload = request.get_json(silent=True) or {}
    try:
        conn = connect_db(_session_from_payload(payload))
        try:
            conn.close()
        except Exception:
            pass
    except ValueError as ex:
        return _test_connection_failed(str(ex))
    except Exception as ex:
        return _test_connection_failed(_friendly_connect_error(ex))
    return ok({"connected": True})
