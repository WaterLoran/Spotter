import json
import queue

from flask import Blueprint, Response, current_app, request, stream_with_context

from redis_eye.db import Base, engine

Base.metadata.create_all(bind=engine)

redis_events_bp = Blueprint("redis_query_events", __name__)


@redis_events_bp.get("/events")
@redis_events_bp.get("/events/")
def sse_events():
    svc = current_app.extensions.get("redis_watch_service")
    if not svc:
        return Response("redis watch unavailable\n", status=503, mimetype="text/plain")

    system_id = request.args.get("system_id", type=int)
    if system_id is None:
        try:
            system_id = int(request.headers.get("X-FastLog-System-Id", "1"))
        except ValueError:
            system_id = 1

    q: queue.Queue = queue.Queue()
    svc.add_listener(q)

    @stream_with_context
    def gen():
        try:
            while True:
                try:
                    line = q.get(timeout=25)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                if not line:
                    continue
                if isinstance(line, str) and line.startswith("data: "):
                    try:
                        json_str = line[6:].strip().split("\n", 1)[0]
                        payload = json.loads(json_str)
                        if payload.get("system_id") != system_id:
                            continue
                    except Exception:
                        pass
                yield line
        finally:
            svc.remove_listener(q)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
