import threading
import time
import uuid
import re
from types import SimpleNamespace
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal

from flask import Blueprint, g, jsonify, request

from sqleye.db import SessionLocal
from sqleye.models import FieldSearchTask, Session
from sqleye.services.db_connector import connect_db
from sqleye.workspace import first_session_for_system, get_session_by_id


field_search_bp = Blueprint("sql_field_search", __name__)
_jobs = {}


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


_EXPR_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")


def _parse_expression(expression: str):
    raw = (expression or "").strip()
    m = _EXPR_RE.match(raw)
    if not m:
        raise ValueError("表达式格式不正确，请使用类似: id = 1")
    field = m.group(1)
    token = m.group(2).strip()
    if (token.startswith("'") and token.endswith("'")) or (token.startswith('"') and token.endswith('"')):
        value = token[1:-1]
    elif token.lower() == "null":
        value = None
    elif token.lower() in ("true", "false"):
        value = token.lower() == "true"
    else:
        try:
            value = int(token)
        except ValueError:
            try:
                value = float(token)
            except ValueError:
                value = token
    return field, value


def _placeholder(db_type: str):
    if db_type == "sqlite":
        return "?"
    if db_type == "oracle":
        return ":1"
    return "%s"


def _quote_ident(db_type: str, ident: str):
    if db_type in ("pgsql", "postgres", "postgresql", "sqlite", "oracle"):
        return f'"{ident}"'
    return f"`{ident}`"


def _normalize_rows(cur, rows):
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return [{str(k): _json_safe_value(v) for k, v in row.items()} for row in rows]
    cols = [d[0] for d in (cur.description or [])]
    result = []
    for row in rows:
        item = {}
        for k, v in dict(zip(cols, row)).items():
            item[str(k)] = _json_safe_value(v)
        result.append(item)
    return result


def _json_safe_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dt_time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    return value


def _normalize_col_row(row):
    """information_schema 行可能是 dict（大小写不一）或 tuple，统一为 table_name / column_name。"""
    if isinstance(row, dict):
        d = {str(k).lower(): v for k, v in row.items()}
        t = d.get("table_name")
        c = d.get("column_name")
        if t is not None and c is not None:
            return {"table_name": t, "column_name": c}
    if isinstance(row, (tuple, list)) and len(row) >= 2:
        return {"table_name": row[0], "column_name": row[1]}
    return None


def _list_columns(cur, db_type: str):
    if db_type == "mysql":
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            ORDER BY table_name, ordinal_position
            """
        )
        rows = cur.fetchall() or []
        out = []
        for r in rows:
            item = _normalize_col_row(r)
            if item:
                out.append(item)
        return out
    if db_type in ("pgsql", "postgres", "postgresql"):
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_name, ordinal_position
            """
        )
        rows = cur.fetchall() or []
        out = []
        for r in rows:
            item = _normalize_col_row(r)
            if item:
                out.append(item)
        return out
    if db_type == "sqlite":
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = cur.fetchall()
        table_names = [t["name"] if isinstance(t, dict) else t[0] for t in tables]
        result = []
        for tname in table_names:
            cur.execute(f'PRAGMA table_info("{tname}")')
            cols = cur.fetchall()
            for c in cols:
                col_name = c["name"] if isinstance(c, dict) else c[1]
                result.append({"table_name": tname, "column_name": col_name})
        return result
    if db_type == "oracle":
        cur.execute(
            """
            SELECT table_name, column_name
            FROM user_tab_columns
            ORDER BY table_name, column_id
            """
        )
        rows = cur.fetchall() or []
        out = []
        for r in rows:
            item = _normalize_col_row(r)
            if item:
                out.append(item)
        return out
    return []


def _run_field_search(session_obj, expression: str, include_value_match: bool):
    db_type = (getattr(session_obj, "db_type", "") or "").strip().lower()
    field, value = _parse_expression(expression)
    conn = connect_db(session_obj)
    try:
        cur = conn.cursor()
        cols = _list_columns(cur, db_type)
        scanned_tables = sorted({str(r["table_name"]) for r in cols if r.get("table_name") is not None})
        exact_matches = []
        value_matches = []
        ph = _placeholder(db_type)
        max_rows_each = 20
        row_limit_sql = (
            f"FETCH FIRST {max_rows_each} ROWS ONLY" if db_type == "oracle" else f"LIMIT {max_rows_each}"
        )

        # Exact match: column name must be exactly the left side field.
        field_lc = field.lower()
        exact_cols = [r for r in cols if str(r.get("column_name", "")).lower() == field_lc]
        for c in exact_cols:
            tname = c["table_name"]
            cname = c["column_name"]
            sql = (
                f"SELECT * FROM {_quote_ident(db_type, tname)} "
                f"WHERE {_quote_ident(db_type, cname)} = {ph} {row_limit_sql}"
            )
            cur.execute(sql, (value,))
            rows = _normalize_rows(cur, cur.fetchall())
            if rows:
                exact_matches.append(
                    {
                        "table": tname,
                        "column": cname,
                        "matched_value": value,
                        "rows": rows,
                    }
                )

        # Optional value match: scan all columns for exact value.
        if include_value_match:
            for c in cols:
                tname = c["table_name"]
                cname = c["column_name"]
                sql = (
                    f"SELECT * FROM {_quote_ident(db_type, tname)} "
                    f"WHERE {_quote_ident(db_type, cname)} = {ph} LIMIT 1"
                )
                try:
                    cur.execute(sql, (value,))
                    rows = _normalize_rows(cur, cur.fetchall())
                except Exception:
                    continue
                if rows:
                    value_matches.append(
                        {
                            "table": tname,
                            "column": cname,
                            "matched_value": value,
                            "sample_rows": rows,
                        }
                    )

        return {
            "expression": expression,
            "exact_matches": exact_matches,
            "value_matches": value_matches,
            "scanned_tables": scanned_tables,
        }
    finally:
        conn.close()


def _field_search_task_for_system(db, task_id):
    return (
        db.query(FieldSearchTask)
        .join(Session, FieldSearchTask.session_id == Session.id)
        .filter(FieldSearchTask.id == int(task_id), Session.system_id == int(g.system_id))
        .first()
    )


@field_search_bp.get("/field-search/tasks")
def list_tasks():
    db = SessionLocal()
    try:
        rows = (
            db.query(FieldSearchTask)
            .join(Session, FieldSearchTask.session_id == Session.id)
            .filter(Session.system_id == int(g.system_id))
            .order_by(FieldSearchTask.id.asc())
            .all()
        )
        return ok([{"id": r.id, "name": r.name, "expression": r.expression, "session_id": r.session_id} for r in rows])
    finally:
        db.close()


@field_search_bp.post("/field-search/tasks")
def create_task():
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        sess = None
        if payload.get("session_id") is not None:
            sess = get_session_by_id(db, g.system_id, payload.get("session_id"))
        if not sess:
            sess = first_session_for_system(db, g.system_id)
        if not sess:
            return jsonify(
                {"success": False, "error": "请先在齿轮菜单中配置至少一份数据库连接", "message": "", "data": None}
            ), 400
        row = FieldSearchTask(
            session_id=sess.id,
            name=payload.get("name", "字段搜索"),
            expression=payload.get("expression", "id = 1"),
        )
        db.add(row)
        db.commit()
        return ok({"id": row.id, "session_id": row.session_id})
    finally:
        db.close()


@field_search_bp.get("/field-search/tasks/<int:task_id>")
def get_task(task_id):
    db = SessionLocal()
    try:
        row = _field_search_task_for_system(db, task_id)
        if not row:
            return ok(None)
        return ok({"id": row.id, "name": row.name, "expression": row.expression, "session_id": row.session_id})
    finally:
        db.close()


@field_search_bp.put("/field-search/tasks/<int:task_id>")
def update_task(task_id):
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = _field_search_task_for_system(db, task_id)
        if not row:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        if "session_id" in payload and payload["session_id"] is not None:
            new_sess = get_session_by_id(db, g.system_id, payload.get("session_id"))
            if not new_sess:
                return jsonify(
                    {"success": False, "error": "所选数据库配置不存在或不属于当前系统", "message": "", "data": None}
                ), 400
            row.session_id = new_sess.id
        row.name = payload.get("name", row.name)
        row.expression = payload.get("expression", row.expression)
        db.commit()
        return ok({"id": row.id, "session_id": row.session_id})
    finally:
        db.close()


@field_search_bp.delete("/field-search/tasks/<int:task_id>")
def delete_task(task_id):
    db = SessionLocal()
    try:
        row = _field_search_task_for_system(db, task_id)
        if not row:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        db.delete(row)
        db.commit()
        return ok()
    finally:
        db.close()


def _session_connect_snapshot(orm_sess: Session) -> SimpleNamespace:
    """在关闭 SQLAlchemy Session 之前取出连接参数，避免 detached 后读属性失败。"""
    return SimpleNamespace(
        db_type=orm_sess.db_type,
        host=orm_sess.host,
        port=orm_sess.port,
        username=orm_sess.username,
        password=orm_sess.password,
        database=orm_sess.database,
    )


@field_search_bp.post("/field-search/<int:session_id>")
def execute_field_search(session_id):
    payload = request.get_json(silent=True) or {}
    include_value_match = bool(payload.get("include_value_match", False))
    expression = payload.get("expression", "")
    db = SessionLocal()
    try:
        sess = db.query(Session).filter(Session.id == int(session_id), Session.system_id == int(g.system_id)).first()
        if not sess:
            return jsonify({"success": False, "error": "未找到对应的 SQL 连接会话"}), 404
        connect_ctx = _session_connect_snapshot(sess)
    finally:
        db.close()

    if include_value_match:
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {"status": "running", "result": None}

        def worker():
            try:
                time.sleep(0.2)
                result = _run_field_search(connect_ctx, expression, include_value_match=True)
                _jobs[job_id] = {"status": "completed", "result": result}
            except Exception as ex:
                _jobs[job_id] = {"status": "error", "error": str(ex), "result": None}

        threading.Thread(target=worker, daemon=True).start()
        return ok({"background": True, "job_id": job_id})
    try:
        result = _run_field_search(connect_ctx, expression, include_value_match=False)
        return ok({"background": False, "result": result})
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex)}), 400


@field_search_bp.get("/field-search/background/<job_id>")
def field_search_bg(job_id):
    return ok(_jobs.get(job_id, {"status": "not_found"}))
