from typing import Optional

from flask import Blueprint, g, jsonify, request

from sqleye.db import Base, SessionLocal, engine
from sqleye.models import FieldSearchTask, QueryHistory, QueryTask, Session  # noqa: F401
from sqleye.services.db_connector import connect_db


sql_sessions_bp = Blueprint("sql_sessions", __name__)
Base.metadata.create_all(bind=engine)


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


def err(message, code=400):
    return jsonify({"success": False, "error": message, "message": "", "data": None}), code


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


def _session_to_dict(row: Session):
    return {
        "id": row.id,
        "name": row.name,
        "db_type": row.db_type,
        "host": row.host,
        "port": row.port,
        "username": row.username,
        "password": row.password,
        "database": row.database,
    }


def _normalize_db_type(raw) -> Optional[str]:
    if raw is None or raw == "":
        return None
    s = str(raw).strip().lower()
    if s in ("mysql", "pgsql", "postgres", "postgresql"):
        if s in ("postgres", "postgresql"):
            return "pgsql"
        return s
    return None


def _test_connection_failed(message: str):
    return jsonify({"success": False, "error": message, "message": "", "data": {"connected": False}})


def _friendly_connect_error(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 400:
        text = text[:400] + "…"
    return f"无法连接数据库: {text}"


@sql_sessions_bp.get("/sessions")
def list_sessions():
    """List all SQL connections for current system. Optional ?db_type=mysql|pgsql."""
    db_type = _normalize_db_type(request.args.get("db_type"))
    db = SessionLocal()
    try:
        q = db.query(Session).filter(Session.system_id == int(g.system_id))
        if db_type:
            q = q.filter(Session.db_type == db_type)
        rows = q.order_by(Session.db_type.asc(), Session.id.asc()).all()
        return ok([_session_to_dict(r) for r in rows])
    finally:
        db.close()


@sql_sessions_bp.post("/sessions")
def create_session():
    payload = request.get_json(silent=True) or {}
    db_type = _normalize_db_type(payload.get("db_type"))
    if db_type not in ("mysql", "pgsql"):
        return err("db_type 必须为 mysql 或 pgsql", 400)
    name = (payload.get("name") or "").strip()
    if not name:
        return err("名称不能为空", 400)
    host = (payload.get("host") or "").strip() or "127.0.0.1"
    database = (payload.get("database") or "").strip()
    if not database:
        return err("数据库名不能为空", 400)
    username = payload.get("username")
    if username is None or str(username).strip() == "":
        return err("用户名不能为空", 400)
    password = payload.get("password")
    if password is None:
        password = ""
    port = payload.get("port")
    try:
        port = int(port) if port is not None and port != "" else (5432 if db_type == "pgsql" else 3306)
    except (TypeError, ValueError):
        return err("端口必须是有效数字", 400)

    db = SessionLocal()
    try:
        dup = (
            db.query(Session)
            .filter(
                Session.system_id == int(g.system_id),
                Session.db_type == db_type,
                Session.name == name,
            )
            .first()
        )
        if dup:
            return err("该类型下已存在同名连接，请更换名称", 400)
        row = Session(
            system_id=int(g.system_id),
            name=name,
            db_type=db_type,
            host=host,
            port=port,
            username=str(username).strip(),
            password=str(password),
            database=database,
        )
        db.add(row)
        db.commit()
        out = _session_to_dict(row)
        return ok(out)
    except Exception as ex:
        db.rollback()
        return err(str(ex), 400)
    finally:
        db.close()


@sql_sessions_bp.put("/sessions/<int:sid>")
def update_session(sid: int):
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.query(Session).filter(Session.id == sid, Session.system_id == int(g.system_id)).first()
        if not row:
            return err("连接不存在", 404)
        if "db_type" in payload:
            db_type = _normalize_db_type(payload.get("db_type"))
            if db_type not in ("mysql", "pgsql"):
                return err("db_type 必须为 mysql 或 pgsql", 400)
            row.db_type = db_type
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                return err("名称不能为空", 400)
            dup = (
                db.query(Session)
                .filter(
                    Session.system_id == int(g.system_id),
                    Session.db_type == row.db_type,
                    Session.name == name,
                    Session.id != sid,
                )
                .first()
            )
            if dup:
                return err("该类型下已存在同名连接，请更换名称", 400)
            row.name = name
        for k in ("host", "port", "username", "password", "database"):
            if k not in payload:
                continue
            if k == "port":
                try:
                    row.port = int(payload[k]) if payload[k] is not None and payload[k] != "" else row.port
                except (TypeError, ValueError):
                    return err("端口必须是有效数字", 400)
            elif k == "password":
                row.password = str(payload[k]) if payload[k] is not None else ""
            else:
                setattr(row, k, payload[k])
        db.commit()
        out = _session_to_dict(row)
        return ok(out)
    except Exception as ex:
        db.rollback()
        return err(str(ex), 400)
    finally:
        db.close()


@sql_sessions_bp.delete("/sessions/<int:sid>")
def delete_session(sid: int):
    db = SessionLocal()
    try:
        row = db.query(Session).filter(Session.id == sid, Session.system_id == int(g.system_id)).first()
        if not row:
            return err("连接不存在", 404)
        qt = db.query(QueryTask).filter(QueryTask.session_id == sid).first()
        if qt:
            return err("仍有 SQL 查询任务引用该连接，请先在任务中更换「数据库配置」后再删除", 400)
        ft = db.query(FieldSearchTask).filter(FieldSearchTask.session_id == sid).first()
        if ft:
            return err("仍有字段搜索任务引用该连接，请先在任务中更换「数据库配置」后再删除", 400)
        db.delete(row)
        db.commit()
        return ok()
    except Exception as ex:
        db.rollback()
        return err(str(ex), 400)
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
