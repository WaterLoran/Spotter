from flask import Blueprint, g, jsonify, request

from redis_eye.db import Base, SessionLocal, engine
from redis_eye.models import RedisSession, RedisTask  # noqa: F401
from redis_eye.services.redis_watch_service import build_redis_client, check_notify_keyspace_events

Base.metadata.create_all(bind=engine)

redis_sessions_bp = Blueprint("redis_query_sessions", __name__)


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


def _session_dict(r: RedisSession):
    return {
        "id": r.id,
        "name": r.name,
        "host": r.host,
        "port": int(r.port),
        "password": r.password or "",
        "db_index": int(r.db_index),
        "use_ssl": bool(r.use_ssl),
        "created_at": str(r.created_at) if r.created_at else "",
        "updated_at": str(r.updated_at) if r.updated_at else "",
    }


def _notify_reload():
    from flask import current_app

    svc = current_app.extensions.get("redis_watch_service")
    if svc:
        svc.reload_from_db()


@redis_sessions_bp.get("/sessions")
@redis_sessions_bp.get("/sessions/")
def list_sessions():
    db = SessionLocal()
    try:
        rows = (
            db.query(RedisSession)
            .filter(RedisSession.system_id == g.system_id)
            .order_by(RedisSession.id.asc())
            .all()
        )
        return ok([_session_dict(r) for r in rows])
    finally:
        db.close()


@redis_sessions_bp.post("/sessions")
@redis_sessions_bp.post("/sessions/")
def create_session():
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = RedisSession(
            system_id=g.system_id,
            name=payload.get("name", "Redis 连接"),
            host=str(payload.get("host", "127.0.0.1")).strip() or "127.0.0.1",
            port=int(payload.get("port", 6379)),
            password=(payload.get("password") or None),
            db_index=int(payload.get("db_index", 0)),
            use_ssl=bool(payload.get("use_ssl", False)),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        _notify_reload()
        return ok({"id": row.id})
    except Exception as ex:
        db.rollback()
        return jsonify({"success": False, "error": str(ex), "message": "", "data": None}), 400
    finally:
        db.close()


@redis_sessions_bp.put("/sessions/<int:sid>")
@redis_sessions_bp.put("/sessions/<int:sid>/")
def update_session(sid):
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.get(RedisSession, sid)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "连接不存在", "message": "", "data": None}), 404
        if "name" in payload:
            row.name = payload["name"]
        if "host" in payload:
            row.host = str(payload["host"] or "").strip() or row.host
        if "port" in payload:
            row.port = int(payload["port"])
        if "password" in payload:
            row.password = payload["password"] or None
        if "db_index" in payload:
            row.db_index = int(payload["db_index"])
        if "use_ssl" in payload:
            row.use_ssl = bool(payload["use_ssl"])
        db.commit()
        _notify_reload()
        return ok({"id": row.id})
    finally:
        db.close()


@redis_sessions_bp.delete("/sessions/<int:sid>")
@redis_sessions_bp.delete("/sessions/<int:sid>/")
def delete_session(sid):
    db = SessionLocal()
    try:
        row = db.get(RedisSession, sid)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "连接不存在", "message": "", "data": None}), 404
        db.delete(row)
        db.commit()
        _notify_reload()
        return ok()
    finally:
        db.close()


@redis_sessions_bp.post("/sessions/test")
@redis_sessions_bp.post("/sessions/test/")
def test_session():
    """测试连接（可不保存），校验 notify-keyspace-events。"""
    payload = request.get_json(silent=True) or {}
    tmp = RedisSession(
        system_id=g.system_id,
        name="_test_",
        host=str(payload.get("host", "127.0.0.1")).strip() or "127.0.0.1",
        port=int(payload.get("port", 6379)),
        password=(payload.get("password") or None),
        db_index=int(payload.get("db_index", 0)),
        use_ssl=bool(payload.get("use_ssl", False)),
    )
    client = None
    try:
        client = build_redis_client(tmp)
        client.ping()
        ok_notify, notify_msg = check_notify_keyspace_events(client)
        return ok({"ping": True, "notify_keyspace_events_ok": ok_notify, "notify_keyspace_events_detail": notify_msg})
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex), "message": "", "data": None}), 200
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
