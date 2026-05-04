from flask import Blueprint, g, jsonify, request

from sqleye.db import SessionLocal
from sqleye.models import QueryHistory, QueryTask, Session
from sqleye.services.diff_detector import detect_diff, result_hash
from sqleye.services.query_executor import execute_sql
from sqleye.workspace import first_session_for_system, get_session_by_id


sql_queries_bp = Blueprint("sql_queries", __name__)


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


def _task_row_dict(r: QueryTask):
    return {
        "id": r.id,
        "session_id": r.session_id,
        "name": r.name,
        "sql": r.sql,
        "polling_interval": r.polling_interval,
        "is_active": r.is_active,
    }


def _query_task_for_system(db, query_id):
    """QueryTask row that belongs to current system (via Session.system_id)."""
    return (
        db.query(QueryTask)
        .join(Session, QueryTask.session_id == Session.id)
        .filter(QueryTask.id == int(query_id), Session.system_id == int(g.system_id))
        .first()
    )


@sql_queries_bp.get("/queries")
def list_queries():
    db = SessionLocal()
    try:
        rows = (
            db.query(QueryTask)
            .join(Session, QueryTask.session_id == Session.id)
            .filter(Session.system_id == int(g.system_id))
            .order_by(QueryTask.id.asc())
            .all()
        )
        return ok([_task_row_dict(r) for r in rows])
    finally:
        db.close()


@sql_queries_bp.post("/queries")
def create_query():
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
        row = QueryTask(
            session_id=sess.id,
            name=payload.get("name", "查询任务"),
            sql=payload.get("sql", "SELECT 1"),
            polling_interval=int(payload.get("polling_interval", 60)),
            is_active=bool(payload.get("is_active", False)),
        )
        db.add(row)
        db.commit()
        return ok({"id": row.id, "session_id": row.session_id})
    finally:
        db.close()


@sql_queries_bp.put("/queries/<int:query_id>")
def update_query(query_id):
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = _query_task_for_system(db, query_id)
        if not row:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        if "session_id" in payload and payload["session_id"] is not None:
            new_sess = get_session_by_id(db, g.system_id, payload.get("session_id"))
            if not new_sess:
                return jsonify({"success": False, "error": "所选数据库配置不存在或不属于当前系统", "message": "", "data": None}), 400
            row.session_id = new_sess.id
        for k in ["name", "sql", "polling_interval", "is_active"]:
            if k in payload:
                setattr(row, k, payload[k])
        db.commit()
        return ok({"id": row.id, "session_id": row.session_id})
    finally:
        db.close()


@sql_queries_bp.delete("/queries/<int:query_id>")
def delete_query(query_id):
    db = SessionLocal()
    try:
        row = _query_task_for_system(db, query_id)
        if not row:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        db.delete(row)
        db.commit()
        return ok()
    finally:
        db.close()


@sql_queries_bp.get("/queries/<int:query_id>/history")
def query_history(query_id):
    db = SessionLocal()
    try:
        task = _query_task_for_system(db, query_id)
        if not task:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        rows = (
            db.query(QueryHistory)
            .filter(QueryHistory.query_task_id == query_id)
            .order_by(QueryHistory.executed_at.desc(), QueryHistory.id.desc())
            .limit(100)
            .all()
        )
        return ok(
            [
                {
                    "id": r.id,
                    "result_data": r.result_data,
                    "result_hash": r.result_hash,
                    "executed_at": str(r.executed_at),
                    "is_different": r.is_different,
                    "diff_markers": r.diff_markers,
                }
                for r in rows
            ]
        )
    finally:
        db.close()


def _delete_query_history_response(query_id, hid):
    db = SessionLocal()
    try:
        task = _query_task_for_system(db, query_id)
        if not task:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        hist = db.get(QueryHistory, hid)
        if not hist or hist.query_task_id != query_id:
            return jsonify({"success": False, "error": "历史记录不存在", "message": "", "data": None}), 404
        if hist.session_id != task.session_id:
            return jsonify({"success": False, "error": "无权删除该历史记录", "message": "", "data": None}), 403
        db.delete(hist)
        db.commit()
        return ok()
    finally:
        db.close()


@sql_queries_bp.delete("/queries/<int:query_id>/history/<int:hid>")
def delete_query_history(query_id, hid):
    return _delete_query_history_response(query_id, hid)


@sql_queries_bp.post("/queries/<int:query_id>/history/<int:hid>/delete")
def delete_query_history_post(query_id, hid):
    """与 DELETE 等价；部分反向代理/旧进程对 DELETE 返回 405 时使用 POST。"""
    return _delete_query_history_response(query_id, hid)


@sql_queries_bp.post("/queries/<int:query_id>/execute")
def execute_query(query_id):
    db = SessionLocal()
    try:
        task = _query_task_for_system(db, query_id)
        if not task:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        sess = get_session_by_id(db, g.system_id, task.session_id)
        if not sess:
            return jsonify(
                {"success": False, "error": "任务绑定的数据库配置已失效，请重新选择「数据库配置」", "message": "", "data": None}
            ), 400
        try:
            rows = execute_sql(sess, task.sql)
        except Exception as ex:
            return jsonify({"success": False, "error": f"执行失败: {ex}", "message": "", "data": None}), 200
        try:
            hash_now = result_hash(rows)
            prev = (
                db.query(QueryHistory)
                .filter(QueryHistory.query_task_id == query_id)
                .order_by(QueryHistory.executed_at.desc(), QueryHistory.id.desc())
                .first()
            )
            prev_rows = prev.result_data if prev and prev.result_data is not None else []
            diff = detect_diff(prev_rows, rows)
            if prev and prev.result_hash == hash_now:
                return ok(
                    {
                        "history_id": prev.id,
                        "rows": rows,
                        "is_different": False,
                        "diff_markers": diff,
                        "history_appended": False,
                    }
                )
            history = QueryHistory(
                query_task_id=query_id,
                session_id=sess.id,
                result_data=rows,
                result_hash=hash_now,
                is_different=(not prev) or (prev.result_hash != hash_now),
                diff_markers=diff,
            )
            db.add(history)
            db.commit()
            return ok(
                {
                    "history_id": history.id,
                    "rows": rows,
                    "is_different": history.is_different,
                    "diff_markers": diff,
                    "history_appended": True,
                }
            )
        except Exception as ex:
            db.rollback()
            return jsonify({"success": False, "error": f"保存执行结果失败: {ex}", "message": "", "data": None}), 200
    finally:
        db.close()
