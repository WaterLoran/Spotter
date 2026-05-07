"""Redis 键空间订阅：PSUBSCRIBE __keyspace@db__:*，命中后 GET 并写库、SSE 广播。"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from redis_eye.db import SessionLocal
from redis_eye.models import RedisSession, RedisTask, RedisTaskHistory
from redis_eye.services.redis_value import fetch_value_display

log = logging.getLogger("redis_eye.watch")

KEYSPACE_CHANNEL_RE = re.compile(r"^__keyspace@(\d+)__:(.*)$")
HISTORY_CAP = 500


def parse_keyspace_channel(channel: str) -> tuple[Optional[int], Optional[str]]:
    if not channel:
        return None, None
    m = KEYSPACE_CHANNEL_RE.match(channel)
    if not m:
        return None, None
    try:
        db = int(m.group(1))
    except ValueError:
        return None, None
    return db, m.group(2)


def build_redis_client(sess: RedisSession):
    import redis

    kwargs = {
        "host": sess.host,
        "port": int(sess.port),
        "db": int(sess.db_index),
        "decode_responses": True,
        "socket_connect_timeout": 5,
        "socket_timeout": None,
    }
    if sess.password:
        kwargs["password"] = sess.password
    if sess.use_ssl:
        kwargs["ssl"] = True
    return redis.Redis(**kwargs)


def check_notify_keyspace_events(client) -> tuple[bool, str]:
    """返回 (是否可用, 说明文案)。"""
    try:
        raw = client.config_get("notify-keyspace-events")
    except Exception as ex:
        return False, f"无法读取 notify-keyspace-events（可能没有 CONFIG 权限）: {ex}"
    if not raw:
        return False, "notify-keyspace-events 未配置"
    v = ""
    if isinstance(raw, dict):
        v = next(iter(raw.values()), "") or ""
    else:
        v = str(raw)
    v = str(v).strip().upper()
    if not v:
        return False, "notify-keyspace-events 为空，请在 Redis 执行 CONFIG SET notify-keyspace-events KEA 或在 redis.conf 中配置"
    if "K" not in v:
        return False, f"notify-keyspace-events 需包含键空间事件（建议 KEA），当前: {v}"
    return True, v


@dataclass
class SessionTaskIndex:
    session_id: int
    system_id: int
    db_index: int
    keys_to_task_ids: Dict[str, List[int]] = field(default_factory=dict)


class RedisWatchService:
    def __init__(self, app: Any = None):
        self._app = app
        self._lock = threading.RLock()
        self._listeners: List[queue.Queue] = []
        self._index: Dict[int, SessionTaskIndex] = {}
        self._workers: Dict[int, "_PubSubWorker"] = {}
        self._started = False

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            self.reload_from_db()

    def add_listener(self, q: queue.Queue):
        with self._lock:
            self._listeners.append(q)

    def remove_listener(self, q: queue.Queue):
        with self._lock:
            try:
                self._listeners.remove(q)
            except ValueError:
                pass

    def emit(self, payload: dict):
        """对外推送 SSE（如标记已读）。"""
        self._broadcast(payload)

    def _broadcast(self, payload: dict):
        data = json.dumps(payload, default=str)
        line = f"data: {data}\n\n"
        with self._lock:
            dead = []
            for q in self._listeners:
                try:
                    q.put_nowait(line)
                except Exception:
                    dead.append(q)
            for q in dead:
                try:
                    self._listeners.remove(q)
                except ValueError:
                    pass

    def reload_from_db(self):
        """从数据库重建订阅索引并启停 worker。"""
        db = SessionLocal()
        try:
            tasks = (
                db.query(RedisTask)
                .join(RedisSession, RedisTask.redis_session_id == RedisSession.id)
                .order_by(RedisTask.id.asc())
                .all()
            )
            new_index: Dict[int, SessionTaskIndex] = {}
            for t in tasks:
                sid = int(t.redis_session_id)
                if sid not in new_index:
                    rs = db.get(RedisSession, sid)
                    if not rs:
                        continue
                    new_index[sid] = SessionTaskIndex(
                        session_id=sid,
                        system_id=int(rs.system_id),
                        db_index=int(rs.db_index),
                        keys_to_task_ids={},
                    )
                idx = new_index[sid]
                k = str(t.redis_key or "")
                idx.keys_to_task_ids.setdefault(k, []).append(int(t.id))
        finally:
            db.close()

        with self._lock:
            self._index = new_index
            wanted: Set[int] = set(new_index.keys())
            for sid in list(self._workers.keys()):
                if sid not in wanted:
                    self._workers[sid].stop()
                    del self._workers[sid]
            for sid in wanted:
                if sid not in self._workers:
                    self._workers[sid] = _PubSubWorker(self, sid)
                    self._workers[sid].start()

    def on_keyspace_message(self, session_id: int, channel: str, _data: str):
        dbn, rkey = parse_keyspace_channel(channel)
        if dbn is None or rkey is None:
            return
        with self._lock:
            idx = self._index.get(session_id)
        if not idx or int(idx.db_index) != int(dbn):
            return
        task_ids = idx.keys_to_task_ids.get(rkey) or []
        if not task_ids:
            return
        db = SessionLocal()
        try:
            sess_row = db.get(RedisSession, session_id)
            if not sess_row:
                return
            client = build_redis_client(sess_row)
            try:
                for tid in task_ids:
                    self._apply_task_value(db, client, tid, source="keyspace")
                db.commit()
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception:
            db.rollback()
            log.exception("on_keyspace_message failed session_id=%s channel=%s", session_id, channel)
        finally:
            db.close()

    def refresh_task_value(self, system_id: int, task_id: int) -> dict:
        """供 HTTP 手动刷新：读 Redis 并更新任务。"""
        db = SessionLocal()
        try:
            task = db.get(RedisTask, task_id)
            if not task or int(task.system_id) != int(system_id):
                return {"success": False, "error": "任务不存在"}
            sess_row = db.get(RedisSession, int(task.redis_session_id))
            if not sess_row:
                return {"success": False, "error": "连接不存在"}
            client = build_redis_client(sess_row)
            try:
                payload = self._apply_task_value(db, client, int(task.id), source="refresh")
                db.commit()
                return {"success": True, "data": payload}
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception as ex:
            db.rollback()
            log.exception("refresh_task_value task_id=%s", task_id)
            return {"success": False, "error": str(ex)}
        finally:
            db.close()

    def _apply_task_value(self, db, client, task_id: int, source: str) -> Optional[dict]:
        task = db.get(RedisTask, task_id)
        if not task:
            return None
        text, vtype = fetch_value_display(client, task.redis_key)
        prev = task.latest_value
        changed = prev != text

        if not changed:
            if source == "refresh":
                return {
                    "type": "task_update",
                    "source": source,
                    "unchanged": True,
                    "system_id": int(task.system_id),
                    "task_id": int(task.id),
                    "latest_value": task.latest_value,
                    "latest_value_type": task.latest_value_type,
                    "last_changed_at": str(task.last_changed_at) if task.last_changed_at else None,
                    "change_count_since_seen": int(task.change_count_since_seen or 0),
                    "history": None,
                }
            return None

        task.latest_value = text
        task.latest_value_type = vtype
        task.last_changed_at = datetime.now()
        if prev is not None:
            task.change_count_since_seen = int(task.change_count_since_seen or 0) + 1
        hist = RedisTaskHistory(task_id=task.id, value=text, value_type=vtype)
        db.add(hist)
        db.flush()
        history_row = {
            "id": hist.id,
            "value": text,
            "value_type": vtype,
            "recorded_at": str(hist.recorded_at),
        }
        _trim_history(db, task.id)

        db.refresh(task)
        payload = {
            "type": "task_update",
            "source": source,
            "system_id": int(task.system_id),
            "task_id": int(task.id),
            "latest_value": task.latest_value,
            "latest_value_type": task.latest_value_type,
            "last_changed_at": str(task.last_changed_at) if task.last_changed_at else None,
            "change_count_since_seen": int(task.change_count_since_seen or 0),
            "history": history_row,
        }
        self._broadcast(payload)
        return payload


def _trim_history(db, task_id: int):
    """保留最近 HISTORY_CAP 条，删除更早的记录。"""
    from sqlalchemy import func

    cnt = db.query(func.count(RedisTaskHistory.id)).filter(RedisTaskHistory.task_id == task_id).scalar()
    cnt = int(cnt or 0)
    if cnt <= HISTORY_CAP:
        return
    n_drop = cnt - HISTORY_CAP
    old_ids = (
        db.query(RedisTaskHistory.id)
        .filter(RedisTaskHistory.task_id == task_id)
        .order_by(RedisTaskHistory.recorded_at.asc(), RedisTaskHistory.id.asc())
        .limit(n_drop)
        .all()
    )
    ids = [r[0] for r in old_ids]
    if ids:
        db.query(RedisTaskHistory).filter(RedisTaskHistory.id.in_(ids)).delete(synchronize_session=False)


class _PubSubWorker:
    def __init__(self, service: RedisWatchService, session_id: int):
        self._service = service
        self._session_id = session_id
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._client = None
        self._pubsub = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name=f"redis-psub-{self._session_id}", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self._pubsub is not None:
                self._pubsub.close()
        except Exception:
            pass
        try:
            if self._client is not None:
                self._client.close()
        except Exception:
            pass
        self._pubsub = None
        self._client = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _run(self):
        db = SessionLocal()
        try:
            sess_row = db.get(RedisSession, self._session_id)
        finally:
            db.close()
        if not sess_row:
            return
        client = None
        pubsub = None
        try:
            client = build_redis_client(sess_row)
            self._client = client
            ok, msg = check_notify_keyspace_events(client)
            if not ok:
                log.warning("redis session %s notify check: %s", self._session_id, msg)
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            self._pubsub = pubsub
            pattern = f"__keyspace@{int(sess_row.db_index)}__:*"
            pubsub.psubscribe(pattern)
            while not self._stop.is_set():
                msg = pubsub.get_message(timeout=1.0)
                if not msg:
                    continue
                if msg.get("type") not in ("pmessage", "message"):
                    continue
                ch = msg.get("channel")
                if isinstance(ch, bytes):
                    ch = ch.decode("utf-8", errors="replace")
                data = msg.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                self._service.on_keyspace_message(self._session_id, ch or "", str(data or ""))
        except Exception:
            log.exception("PubSubWorker session_id=%s crashed", self._session_id)
        finally:
            try:
                if pubsub:
                    pubsub.close()
            except Exception:
                pass
            try:
                if client:
                    client.close()
            except Exception:
                pass
            self._pubsub = None
            self._client = None
