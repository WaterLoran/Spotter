from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import desc, func

from redis_eye.db import Base, SessionLocal, engine
from redis_eye.models import RedisSession, RedisTask, RedisTaskHistory  # noqa: F401

Base.metadata.create_all(bind=engine)

redis_tasks_bp = Blueprint("redis_query_tasks", __name__)


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


def _notify_reload():
    svc = current_app.extensions.get("redis_watch_service")
    if svc:
        svc.reload_from_db()


def _clamp_percent(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 10
    return max(1, min(100, n))


def _task_dict(r: RedisTask):
    return {
        "id": r.id,
        "system_id": r.system_id,
        "redis_session_id": r.redis_session_id,
        "name": r.name,
        "redis_key": r.redis_key,
        "color_step_percent": int(r.color_step_percent or 10),
        "display_order": int(r.display_order or 0),
        "latest_value": r.latest_value,
        "latest_value_type": r.latest_value_type,
        "last_changed_at": str(r.last_changed_at) if r.last_changed_at else None,
        "change_count_since_seen": int(r.change_count_since_seen or 0),
        "created_at": str(r.created_at) if r.created_at else "",
        "updated_at": str(r.updated_at) if r.updated_at else "",
    }


@redis_tasks_bp.get("/tasks")
@redis_tasks_bp.get("/tasks/")
def list_tasks():
    db = SessionLocal()
    try:
        rows = (
            db.query(RedisTask)
            .filter(RedisTask.system_id == g.system_id)
            .order_by(RedisTask.display_order.asc(), RedisTask.id.asc())
            .all()
        )
        return ok([_task_dict(r) for r in rows])
    finally:
        db.close()


@redis_tasks_bp.post("/tasks")
@redis_tasks_bp.post("/tasks/")
def create_task():
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        if payload.get("redis_session_id") in (None, ""):
            return jsonify({"success": False, "error": "请选择 Redis 连接", "message": "", "data": None}), 400
        sid = int(payload.get("redis_session_id"))
        sess = db.get(RedisSession, sid)
        if not sess or sess.system_id != g.system_id:
            return jsonify({"success": False, "error": "Redis 连接不存在", "message": "", "data": None}), 400
        mx = db.query(func.coalesce(func.max(RedisTask.display_order), 0)).filter(RedisTask.system_id == g.system_id).scalar()
        order = int(mx or 0) + 1
        row = RedisTask(
            system_id=g.system_id,
            redis_session_id=sid,
            name=payload.get("name", "Redis 任务"),
            redis_key=str(payload.get("redis_key", "")).strip(),
            color_step_percent=_clamp_percent(payload.get("color_step_percent", 10)),
            display_order=order,
        )
        if not row.redis_key:
            return jsonify({"success": False, "error": "请填写 key", "message": "", "data": None}), 400
        db.add(row)
        db.commit()
        db.refresh(row)
        _notify_reload()
        svc = current_app.extensions.get("redis_watch_service")
        if svc:
            res = svc.refresh_task_value(g.system_id, row.id)
            if not res.get("success"):
                pass
        return ok({"id": row.id})
    finally:
        db.close()


@redis_tasks_bp.put("/tasks/<int:tid>")
@redis_tasks_bp.put("/tasks/<int:tid>/")
def update_task(tid):
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.get(RedisTask, tid)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        if "redis_session_id" in payload:
            sid = int(payload["redis_session_id"])
            sess = db.get(RedisSession, sid)
            if not sess or sess.system_id != g.system_id:
                return jsonify({"success": False, "error": "Redis 连接不存在", "message": "", "data": None}), 400
            row.redis_session_id = sid
        if "name" in payload:
            row.name = payload["name"]
        if "redis_key" in payload:
            k = str(payload["redis_key"] or "").strip()
            if not k:
                return jsonify({"success": False, "error": "请填写 key", "message": "", "data": None}), 400
            row.redis_key = k
        if "color_step_percent" in payload:
            row.color_step_percent = _clamp_percent(payload["color_step_percent"])
        if "display_order" in payload:
            row.display_order = int(payload["display_order"])
        db.commit()
        _notify_reload()
        svc = current_app.extensions.get("redis_watch_service")
        if svc and ("redis_key" in payload or "redis_session_id" in payload):
            svc.refresh_task_value(g.system_id, row.id)
        return ok({"id": row.id})
    finally:
        db.close()


@redis_tasks_bp.delete("/tasks/<int:tid>")
@redis_tasks_bp.delete("/tasks/<int:tid>/")
def delete_task(tid):
    db = SessionLocal()
    try:
        row = db.get(RedisTask, tid)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        db.delete(row)
        db.commit()
        _notify_reload()
        return ok()
    finally:
        db.close()


@redis_tasks_bp.put("/tasks/order")
@redis_tasks_bp.put("/tasks/order/")
def order_tasks():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("order") or []
    if not isinstance(ids, list):
        return jsonify({"success": False, "error": "order 须为 id 数组", "message": "", "data": None}), 400
    db = SessionLocal()
    try:
        for i, raw_id in enumerate(ids):
            tid = int(raw_id)
            row = db.get(RedisTask, tid)
            if row and row.system_id == g.system_id:
                row.display_order = i + 1
        db.commit()
        _notify_reload()
        return ok()
    finally:
        db.close()


@redis_tasks_bp.post("/tasks/<int:tid>/refresh")
@redis_tasks_bp.post("/tasks/<int:tid>/refresh/")
def refresh_task(tid):
    svc = current_app.extensions.get("redis_watch_service")
    if not svc:
        return jsonify({"success": False, "error": "Redis 监听服务未启动", "message": "", "data": None}), 503
    res = svc.refresh_task_value(g.system_id, tid)
    if not res.get("success"):
        return jsonify({"success": False, "error": res.get("error", "刷新失败"), "message": "", "data": None}), 200
    return ok(res.get("data"))


@redis_tasks_bp.post("/tasks/<int:tid>/seen")
@redis_tasks_bp.post("/tasks/<int:tid>/seen/")
def mark_seen(tid):
    db = SessionLocal()
    try:
        row = db.get(RedisTask, tid)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        row.change_count_since_seen = 0
        db.commit()
        d = _task_dict(row)
        svc = current_app.extensions.get("redis_watch_service")
        if svc:
            svc.emit(
                {
                    "type": "task_update",
                    "source": "seen",
                    "system_id": int(d["system_id"]),
                    "task_id": int(d["id"]),
                    "latest_value": d["latest_value"],
                    "latest_value_type": d["latest_value_type"],
                    "last_changed_at": d["last_changed_at"],
                    "change_count_since_seen": 0,
                    "history": None,
                }
            )
        return ok(d)
    finally:
        db.close()


@redis_tasks_bp.get("/tasks/<int:tid>/history")
@redis_tasks_bp.get("/tasks/<int:tid>/history/")
def task_history(tid):
    limit = request.args.get("limit", default=200, type=int)
    limit = max(1, min(500, limit))
    db = SessionLocal()
    try:
        task = db.get(RedisTask, tid)
        if not task or task.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        rows = (
            db.query(RedisTaskHistory)
            .filter(RedisTaskHistory.task_id == tid)
            .order_by(desc(RedisTaskHistory.recorded_at), desc(RedisTaskHistory.id))
            .limit(limit)
            .all()
        )
        return ok(
            [
                {
                    "id": r.id,
                    "value": r.value,
                    "value_type": r.value_type,
                    "recorded_at": str(r.recorded_at),
                }
                for r in rows
            ]
        )
    finally:
        db.close()


@redis_tasks_bp.delete("/tasks/<int:tid>/history")
@redis_tasks_bp.delete("/tasks/<int:tid>/history/")
def clear_history(tid):
    db = SessionLocal()
    try:
        task = db.get(RedisTask, tid)
        if not task or task.system_id != g.system_id:
            return jsonify({"success": False, "error": "任务不存在", "message": "", "data": None}), 404
        db.query(RedisTaskHistory).filter(RedisTaskHistory.task_id == tid).delete(synchronize_session=False)
        db.commit()
        return ok()
    finally:
        db.close()
