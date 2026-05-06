from flask import Blueprint, g, jsonify, request

from apieye.db import Base, SessionLocal, engine
from apieye.models import ApiHistory, ApiTask, HeaderSnippet  # noqa: F401
from apieye.services.api_executor import execute_http_task, rows_for_history_hash
from apieye.services.header_runner import compute_headers
from sqleye.services.diff_detector import detect_diff, result_hash

Base.metadata.create_all(bind=engine)

api_tasks_bp = Blueprint("api_tasks", __name__)


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


def _task_dict(r: ApiTask):
    return {
        "id": r.id,
        "name": r.name,
        "method": r.method,
        "url": r.url,
        "query_params": r.query_params or [],
        "body_type": r.body_type,
        "body": r.body or "",
        "header_snippet_id": r.header_snippet_id,
        "timeout": r.timeout,
        "polling_interval": r.polling_interval,
        "is_active": bool(r.is_active),
    }


@api_tasks_bp.get("/tasks")
@api_tasks_bp.get("/tasks/")
def list_tasks():
    db = SessionLocal()
    try:
        rows = (
            db.query(ApiTask)
            .filter(ApiTask.system_id == g.system_id)
            .order_by(ApiTask.id.asc())
            .all()
        )
        return ok([_task_dict(r) for r in rows])
    finally:
        db.close()


@api_tasks_bp.post("/tasks")
@api_tasks_bp.post("/tasks/")
def create_task():
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        hid = payload.get("header_snippet_id")
        header_id = None
        if hid is not None and hid != "":
            sn = db.get(HeaderSnippet, int(hid))
            if not sn or sn.system_id != g.system_id:
                return jsonify({"success": False, "error": "Header 代码不存在", "message": "", "data": None}), 400
            header_id = int(hid)
        row = ApiTask(
            system_id=g.system_id,
            name=payload.get("name", "API 任务"),
            method=(payload.get("method") or "GET").upper(),
            url=payload.get("url", ""),
            query_params=payload.get("query_params") or [],
            body_type=payload.get("body_type") or "none",
            body=payload.get("body") or "",
            header_snippet_id=header_id,
            timeout=int(payload.get("timeout", 30)),
            polling_interval=int(payload.get("polling_interval", 60)),
            is_active=bool(payload.get("is_active", False)),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return ok({"id": row.id})
    finally:
        db.close()


@api_tasks_bp.put("/tasks/<int:task_id>")
@api_tasks_bp.put("/tasks/<int:task_id>/")
def update_task(task_id):
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.get(ApiTask, task_id)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        if "header_snippet_id" in payload:
            hid = payload["header_snippet_id"]
            if hid is None:
                row.header_snippet_id = None
            else:
                sn = db.get(HeaderSnippet, int(hid))
                if not sn or sn.system_id != g.system_id:
                    return jsonify({"success": False, "error": "Header 代码不存在", "message": "", "data": None}), 400
                row.header_snippet_id = int(hid)
        for k in ["name", "method", "url", "query_params", "body_type", "body", "timeout", "polling_interval", "is_active"]:
            if k in payload:
                if k == "method":
                    setattr(row, k, str(payload[k] or "GET").upper())
                elif k in ("timeout", "polling_interval"):
                    setattr(row, k, int(payload[k]))
                elif k == "is_active":
                    setattr(row, k, bool(payload[k]))
                else:
                    setattr(row, k, payload[k])
        db.commit()
        return ok({"id": row.id})
    finally:
        db.close()


@api_tasks_bp.delete("/tasks/<int:task_id>")
@api_tasks_bp.delete("/tasks/<int:task_id>/")
def delete_task(task_id):
    db = SessionLocal()
    try:
        row = db.get(ApiTask, task_id)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        db.delete(row)
        db.commit()
        return ok()
    finally:
        db.close()


@api_tasks_bp.get("/tasks/<int:task_id>/history")
@api_tasks_bp.get("/tasks/<int:task_id>/history/")
def task_history(task_id):
    db = SessionLocal()
    try:
        task = db.get(ApiTask, task_id)
        if not task or task.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        rows = (
            db.query(ApiHistory)
            .filter(ApiHistory.api_task_id == task_id)
            .order_by(ApiHistory.executed_at.desc(), ApiHistory.id.desc())
            .limit(100)
            .all()
        )
        return ok(
            [
                {
                    "id": r.id,
                    "status_code": r.status_code,
                    "response_headers": r.response_headers,
                    "response_data": r.response_data,
                    "response_text": r.response_text,
                    "result_data": r.result_data,
                    "result_hash": r.result_hash,
                    "executed_at": str(r.executed_at),
                    "is_different": r.is_different,
                    "diff_markers": r.diff_markers,
                    "error": r.error,
                }
                for r in rows
            ]
        )
    finally:
        db.close()


def _delete_history(task_id, hid):
    db = SessionLocal()
    try:
        task = db.get(ApiTask, task_id)
        if not task or task.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        hist = db.get(ApiHistory, hid)
        if not hist or hist.api_task_id != task_id:
            return jsonify({"success": False, "error": "历史记录不存在", "message": "", "data": None}), 404
        if hist.system_id != g.system_id:
            return jsonify({"success": False, "error": "无权删除", "message": "", "data": None}), 403
        db.delete(hist)
        db.commit()
        return ok()
    finally:
        db.close()


@api_tasks_bp.delete("/tasks/<int:task_id>/history/<int:hid>")
@api_tasks_bp.delete("/tasks/<int:task_id>/history/<int:hid>/")
def delete_history(task_id, hid):
    return _delete_history(task_id, hid)


@api_tasks_bp.post("/tasks/<int:task_id>/execute")
@api_tasks_bp.post("/tasks/<int:task_id>/execute/")
def execute_task(task_id):
    db = SessionLocal()
    try:
        task = db.get(ApiTask, task_id)
        if not task or task.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404

        extra_headers = None
        if task.header_snippet_id:
            sn = db.get(HeaderSnippet, task.header_snippet_id)
            if not sn or sn.system_id != g.system_id:
                return jsonify({"success": False, "error": "关联的 Header 代码不存在", "message": "", "data": None}), 400
            try:
                extra_headers = compute_headers(g.system_id, sn.id, sn.code, sn.ttl_seconds)
            except RuntimeError as ex:
                return jsonify({"success": False, "error": f"Header 代码执行失败: {ex}", "message": "", "data": None}), 200

        try:
            result = execute_http_task(
                task.method,
                task.url,
                task.query_params if isinstance(task.query_params, list) else [],
                task.body_type or "none",
                task.body,
                extra_headers,
                task.timeout,
            )
        except ValueError as ex:
            return jsonify({"success": False, "error": str(ex), "message": "", "data": None}), 200
        except Exception as ex:
            return jsonify({"success": False, "error": f"请求失败: {ex}", "message": "", "data": None}), 200

        status_code = result.get("status_code")
        response_headers = result.get("response_headers")
        response_data = result.get("response_data")
        response_text = result.get("response_text")
        err_msg = result.get("error")

        rows = rows_for_history_hash(status_code, response_data, response_text, err_msg)

        try:
            hash_now = result_hash(rows)
            prev = (
                db.query(ApiHistory)
                .filter(ApiHistory.api_task_id == task_id)
                .order_by(ApiHistory.executed_at.desc(), ApiHistory.id.desc())
                .first()
            )
            prev_rows: list = []
            if prev and getattr(prev, "result_data", None) is not None:
                prev_rows = prev.result_data if isinstance(prev.result_data, list) else []
            diff = detect_diff(prev_rows, rows)

            if prev and prev.result_hash == hash_now:
                return ok(
                    {
                        "history_id": prev.id,
                        "status_code": status_code,
                        "response_headers": response_headers,
                        "response_data": response_data,
                        "response_text": response_text,
                        "rows": rows,
                        "is_different": False,
                        "diff_markers": diff,
                        "history_appended": False,
                        "error": err_msg,
                    }
                )

            history = ApiHistory(
                api_task_id=task_id,
                system_id=g.system_id,
                status_code=status_code,
                response_headers=response_headers,
                response_data=response_data,
                response_text=response_text,
                result_hash=hash_now,
                is_different=(not prev) or (prev.result_hash != hash_now),
                diff_markers=diff,
                error=err_msg,
                result_data=rows,
            )
            db.add(history)
            db.commit()
            return ok(
                {
                    "history_id": history.id,
                    "status_code": status_code,
                    "response_headers": response_headers,
                    "response_data": response_data,
                    "response_text": response_text,
                    "rows": rows,
                    "is_different": history.is_different,
                    "diff_markers": diff,
                    "history_appended": True,
                    "error": err_msg,
                }
            )
        except Exception as ex:
            db.rollback()
            return jsonify(
                {"success": False, "error": f"保存执行结果失败: {ex}", "message": "", "data": None}
            ), 200
    finally:
        db.close()
