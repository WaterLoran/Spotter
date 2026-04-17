from flask import Blueprint, g, jsonify, request

from sqleye.db import SessionLocal
from sqleye.models import QueryHistory, QueryTask
from sqleye.services.diff_detector import detect_diff, result_hash
from sqleye.services.query_executor import execute_sql
from sqleye.workspace import get_workspace_session


sql_queries_bp = Blueprint("sql_queries", __name__)


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


@sql_queries_bp.get("/queries")
def list_queries():
    db = SessionLocal()
    try:
        sess = get_workspace_session(db, g.system_id)
        if not sess:
            return ok([])
        rows = db.query(QueryTask).filter(QueryTask.session_id == sess.id).all()
        return ok([{"id": r.id, "name": r.name, "sql": r.sql, "polling_interval": r.polling_interval, "is_active": r.is_active} for r in rows])
    finally:
        db.close()


@sql_queries_bp.post("/queries")
def create_query():
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        sess = get_workspace_session(db, g.system_id)
        if not sess:
            return jsonify({"success": False, "error": "请先保存 SQL 连接配置", "message": "", "data": None}), 400
        row = QueryTask(
            session_id=sess.id,
            name=payload.get("name", "查询任务"),
            sql=payload.get("sql", "SELECT 1"),
            polling_interval=int(payload.get("polling_interval", 60)),
            is_active=bool(payload.get("is_active", False)),
        )
        db.add(row)
        db.commit()
        return ok({"id": row.id})
    finally:
        db.close()


@sql_queries_bp.put("/queries/<int:query_id>")
def update_query(query_id):
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.get(QueryTask, query_id)
        if not row:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        sess = get_workspace_session(db, g.system_id)
        if not sess or row.session_id != sess.id:
            return jsonify({"success": False, "error": "无权修改该查询（不属于当前系统）", "message": "", "data": None}), 403
        for k in ["name", "sql", "polling_interval", "is_active"]:
            if k in payload:
                setattr(row, k, payload[k])
        db.commit()
        return ok({"id": row.id})
    finally:
        db.close()


@sql_queries_bp.delete("/queries/<int:query_id>")
def delete_query(query_id):
    db = SessionLocal()
    try:
        row = db.get(QueryTask, query_id)
        if not row:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        sess = get_workspace_session(db, g.system_id)
        if not sess or row.session_id != sess.id:
            return jsonify({"success": False, "error": "无权删除该查询（不属于当前系统）", "message": "", "data": None}), 403
        db.delete(row)
        db.commit()
        return ok()
    finally:
        db.close()


@sql_queries_bp.get("/queries/<int:query_id>/history")
def query_history(query_id):
    db = SessionLocal()
    try:
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
        task = db.get(QueryTask, query_id)
        if not task:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        sess = get_workspace_session(db, g.system_id)
        if not sess or task.session_id != sess.id:
            return jsonify({"success": False, "error": "无权操作该查询（不属于当前系统）", "message": "", "data": None}), 403
        hist = db.get(QueryHistory, hid)
        if not hist or hist.query_task_id != query_id:
            return jsonify({"success": False, "error": "历史记录不存在", "message": "", "data": None}), 404
        if hist.session_id != sess.id:
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
        task = db.get(QueryTask, query_id)
        if not task:
            return jsonify({"success": False, "error": "查询任务不存在", "message": "", "data": None}), 404
        sess = get_workspace_session(db, g.system_id)
        if not sess:
            return jsonify({"success": False, "error": "请先保存 SQL 连接配置", "message": "", "data": None}), 400
        if task.session_id != sess.id:
            return jsonify(
                {
                    "success": False,
                    "error": "该查询不属于当前系统（请确认顶部系统与 SQL 列表一致后重试）",
                    "message": "",
                    "data": None,
                }
            ), 400
        try:
            rows = execute_sql(sess, task.sql)
        except Exception as ex:
            return jsonify(
                {"success": False, "error": f"执行失败: {ex}", "message": "", "data": None}
            ), 200
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
            # 仅当「无历史」或「与最近一次已记录快照的 result_hash 不同」时写入新行；
            # 与上一次执行结果一致时不追加历史（首次执行 prev 为空，必写）。
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
            return jsonify(
                {"success": False, "error": f"保存执行结果失败: {ex}", "message": "", "data": None}
            ), 200
    finally:
        db.close()
