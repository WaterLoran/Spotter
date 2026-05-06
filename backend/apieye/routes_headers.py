from flask import Blueprint, g, jsonify, request

from apieye.db import Base, SessionLocal, engine
from apieye.models import ApiTask, HeaderSnippet  # noqa: F401
from apieye.services.header_runner import compute_headers, invalidate

Base.metadata.create_all(bind=engine)

header_snippets_bp = Blueprint("api_header_snippets", __name__)


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


def _task_row(r: HeaderSnippet):
    return {
        "id": r.id,
        "name": r.name,
        "code": r.code,
        "ttl_seconds": r.ttl_seconds,
        "description": r.description or "",
        "created_at": str(r.created_at) if r.created_at else "",
        "updated_at": str(r.updated_at) if r.updated_at else "",
    }


@header_snippets_bp.get("/headers")
@header_snippets_bp.get("/headers/")
def list_headers():
    db = SessionLocal()
    try:
        rows = (
            db.query(HeaderSnippet)
            .filter(HeaderSnippet.system_id == g.system_id)
            .order_by(HeaderSnippet.id.asc())
            .all()
        )
        return ok([_task_row(r) for r in rows])
    finally:
        db.close()


@header_snippets_bp.post("/headers")
@header_snippets_bp.post("/headers/")
def create_header():
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = HeaderSnippet(
            system_id=g.system_id,
            name=payload.get("name", "Header 代码"),
            code=payload.get("code", ""),
            ttl_seconds=int(payload.get("ttl_seconds", 300)),
            description=payload.get("description") or None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        invalidate(row.id)
        return ok({"id": row.id})
    finally:
        db.close()


@header_snippets_bp.put("/headers/<int:sid>")
@header_snippets_bp.put("/headers/<int:sid>/")
def update_header(sid):
    payload = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.get(HeaderSnippet, sid)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "记录不存在", "message": "", "data": None}), 404
        for k in ["name", "code", "ttl_seconds", "description"]:
            if k in payload:
                setattr(row, k, payload[k])
        db.commit()
        invalidate(sid)
        return ok({"id": row.id})
    finally:
        db.close()


@header_snippets_bp.delete("/headers/<int:sid>")
@header_snippets_bp.delete("/headers/<int:sid>/")
def delete_header(sid):
    db = SessionLocal()
    try:
        row = db.get(HeaderSnippet, sid)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "记录不存在", "message": "", "data": None}), 404
        n = db.query(ApiTask).filter(ApiTask.header_snippet_id == sid).count()
        if n:
            return jsonify(
                {
                    "success": False,
                    "error": f"该 Header 代码被 {n} 个任务引用，请先解除引用",
                    "message": "",
                    "data": None,
                }
            ), 400
        db.delete(row)
        db.commit()
        invalidate(sid)
        return ok()
    finally:
        db.close()


@header_snippets_bp.post("/headers/<int:sid>/preview")
@header_snippets_bp.post("/headers/<int:sid>/preview/")
def preview_header(sid):
    db = SessionLocal()
    try:
        row = db.get(HeaderSnippet, sid)
        if not row or row.system_id != g.system_id:
            return jsonify({"success": False, "error": "记录不存在", "message": "", "data": None}), 404
        try:
            headers = compute_headers(g.system_id, row.id, row.code, row.ttl_seconds)
            return ok({"headers": headers})
        except RuntimeError as ex:
            return jsonify({"success": False, "error": str(ex), "message": "", "data": None}), 200
    finally:
        db.close()
